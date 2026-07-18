"""Structured final-author completion packets and journal missing-field reports."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .artifact_dag import record_artifact_change
from .change_impact import change_class_spec
from .evidence_snapshot import EvidenceSnapshotMismatch, validate_promoted_snapshot_for_writing
from .project_scaffold import utc_now
from .project_state import load_project
from .manuscript_revision import (
    LOCKS_PATH,
    REVISION_LEDGER,
    SOURCE_MAP,
    _apply_operation,
    _classify,
    _sha_text,
    add_custom_reference,
    build_manuscript_source_map,
    resolve_manuscript_revision_target as _resolve_manuscript_revision_target,
    set_manuscript_metadata,
)
from .scoped_transaction import ScopedProjectTransaction
from .section_contracts import validate_section_writing
from .state_kernel import atomic_write_bytes, atomic_write_text, append_jsonl_locked
from .write_set_guard import BoundaryViolation, resolve_confined_path


COMPLETION_ROOT = "writing/manuscript_completion"
TEMPLATE_PATH = f"{COMPLETION_ROOT}/template.yaml"
MISSING_FIELDS_PATH = f"{COMPLETION_ROOT}/missing_fields.json"
ACTIVE_MANIFEST_PATH = f"{COMPLETION_ROOT}/active_completion_manifest.json"
PACKET_ROOT = f"{COMPLETION_ROOT}/packets"
COMPLETION_LEDGER_PATH = f"{COMPLETION_ROOT}/completion_ledger.jsonl"
COMPLETION_SCHEMA = "dpl.manuscript_completion.v1"

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "project_id",
    "target_journal",
    "metadata",
    "custom_references",
    "section_revisions",
}
_METADATA_FIELDS = {
    "title",
    "short_title",
    "abstract",
    "keywords",
    "authors",
    "affiliations",
    "corresponding_author",
    "email",
    "orcid",
    "credit_contributions",
    "acknowledgments",
    "funding",
    "data_availability",
    "code_availability",
    "competing_interests",
    "ethics_consent",
    "supplementary_material",
    "repository_links",
    "doi_links",
    "figure_captions",
}
_REFERENCE_FIELDS = {
    "citation_key",
    "entry_type",
    "title",
    "authors",
    "year",
    "journal",
    "booktitle",
    "volume",
    "issue",
    "pages",
    "publisher",
    "doi",
    "url",
    "evidence_notes",
    "evidence_only",
    "intended_sections",
}
_DEFAULT_REQUIRED = ["title", "authors", "affiliations", "abstract"]
_DEFAULT_RECOMMENDED = [
    "short_title",
    "corresponding_author",
    "email",
    "orcid",
    "credit_contributions",
    "acknowledgments",
    "funding",
    "data_availability",
    "code_availability",
    "competing_interests",
]
_PLACEHOLDER_RE = re.compile(
    r"(?:draft author|draft affiliation|author@example|placeholder|to be supplied|your name|todo|tbd|example\.com)",
    flags=re.I,
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ORCID_RE = re.compile(r"^(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-[\dX]{4}$", flags=re.I)


class ManuscriptCompletionError(RuntimeError):
    """Raised when a completion packet is invalid or crosses its authority boundary."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, (list, dict)) and not value)


def _placeholder_fields(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        findings: list[str] = []
        for key, child in value.items():
            findings.extend(_placeholder_fields(child, f"{path}.{key}" if path else str(key)))
        return findings
    if isinstance(value, list):
        findings = []
        for index, child in enumerate(value):
            findings.extend(_placeholder_fields(child, f"{path}[{index}]"))
        return findings
    if isinstance(value, str) and _PLACEHOLDER_RE.search(value):
        return [path]
    return []


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ManuscriptCompletionError(f"metadata.{field} must be a list of non-empty strings.")
    return [item.strip() for item in value]


def _validate_authors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManuscriptCompletionError("metadata.authors must be a list of structured author objects.")
    authors: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ManuscriptCompletionError(f"metadata.authors[{index}] requires a non-empty name.")
        author = dict(item)
        affiliations = author.get("affiliations", [])
        if not isinstance(affiliations, list) or any(not isinstance(entry, str) or not entry.strip() for entry in affiliations):
            raise ManuscriptCompletionError(f"metadata.authors[{index}].affiliations must contain affiliation IDs.")
        if author.get("orcid") and not _ORCID_RE.match(str(author["orcid"]).strip()):
            raise ManuscriptCompletionError(f"metadata.authors[{index}].orcid is invalid.")
        if author.get("email") and not _EMAIL_RE.match(str(author["email"]).strip()):
            raise ManuscriptCompletionError(f"metadata.authors[{index}].email is invalid.")
        authors.append(author)
    return authors


def _validate_affiliations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ManuscriptCompletionError("metadata.affiliations must be a list of structured affiliation objects.")
    affiliations: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip() or not str(item.get("name") or "").strip():
            raise ManuscriptCompletionError(f"metadata.affiliations[{index}] requires non-empty id and name fields.")
        affiliations.append(dict(item))
    return affiliations


def _validate_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ManuscriptCompletionError("metadata must be a mapping.")
    unknown = sorted(set(value) - _METADATA_FIELDS)
    if unknown:
        raise ManuscriptCompletionError("Unsupported metadata fields: " + ", ".join(unknown))
    metadata = dict(value)
    if "authors" in metadata:
        metadata["authors"] = _validate_authors(metadata["authors"])
    if "affiliations" in metadata:
        metadata["affiliations"] = _validate_affiliations(metadata["affiliations"])
    if "keywords" in metadata:
        metadata["keywords"] = _string_list(metadata["keywords"], "keywords")
    for field in ("repository_links", "doi_links"):
        if field in metadata and isinstance(metadata[field], list):
            metadata[field] = _string_list(metadata[field], field)
        elif field in metadata and metadata[field] is not None and not isinstance(metadata[field], str):
            raise ManuscriptCompletionError(f"metadata.{field} must be a string or list of strings.")
    if metadata.get("email") and not _EMAIL_RE.match(str(metadata["email"]).strip()):
        raise ManuscriptCompletionError("metadata.email is invalid.")
    if metadata.get("orcid") and isinstance(metadata["orcid"], str) and not _ORCID_RE.match(metadata["orcid"].strip()):
        raise ManuscriptCompletionError("metadata.orcid is invalid.")
    captions = metadata.get("figure_captions")
    if captions is not None and (
        not isinstance(captions, dict)
        or any(not str(key).strip() or not isinstance(text, str) or not text.strip() for key, text in captions.items())
    ):
        raise ManuscriptCompletionError("metadata.figure_captions must map stable figure IDs to non-empty text.")
    funding = metadata.get("funding")
    if funding is not None and not isinstance(funding, (str, list)):
        raise ManuscriptCompletionError("metadata.funding must be text or a list of structured funding records.")
    if isinstance(funding, list):
        for index, item in enumerate(funding):
            if isinstance(item, str) and item.strip():
                continue
            if isinstance(item, dict) and str(item.get("funder") or "").strip():
                continue
            raise ManuscriptCompletionError(
                f"metadata.funding[{index}] must be non-empty text or a record with a funder."
            )
    return metadata


def _validate_references(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManuscriptCompletionError("custom_references must be a list.")
    references: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManuscriptCompletionError(f"custom_references[{index}] must be a mapping.")
        unknown = sorted(set(item) - _REFERENCE_FIELDS)
        if unknown:
            raise ManuscriptCompletionError(
                f"Unsupported custom_references[{index}] fields: " + ", ".join(unknown)
            )
        required = ("citation_key", "title", "authors", "year", "evidence_notes")
        missing = [field for field in required if _is_empty(item.get(field))]
        if missing:
            raise ManuscriptCompletionError(
                f"custom_references[{index}] is missing: " + ", ".join(missing)
            )
        if not isinstance(item["authors"], list) or any(not str(author).strip() for author in item["authors"]):
            raise ManuscriptCompletionError(f"custom_references[{index}].authors must be a non-empty list.")
        year = item["year"]
        if isinstance(year, bool) or not re.fullmatch(r"\d{4}[a-z]?", str(year).strip(), flags=re.I):
            raise ManuscriptCompletionError(f"custom_references[{index}].year must be a four-digit publication year.")
        references.append(dict(item))
    return references


def validate_manuscript_completion_payload(project: str | Path, payload: Any) -> dict[str, Any]:
    """Validate and normalize a completion payload without applying any changes."""
    state = load_project(project)
    if not isinstance(payload, dict):
        raise ManuscriptCompletionError("Completion payload must be a YAML/JSON object.")
    unknown = sorted(set(payload) - _TOP_LEVEL_FIELDS)
    if unknown:
        raise ManuscriptCompletionError("Unsupported completion fields: " + ", ".join(unknown))
    if str(payload.get("schema_version") or "") != COMPLETION_SCHEMA:
        raise ManuscriptCompletionError(f"schema_version must be {COMPLETION_SCHEMA}.")
    expected_project_id = str(state.metadata.get("project_id") or "")
    if str(payload.get("project_id") or "") != expected_project_id:
        raise ManuscriptCompletionError("Completion project_id does not match the target project.")
    target_journal = str(payload.get("target_journal") or state.metadata.get("target_journal") or "").strip()
    expected_journal = str(state.metadata.get("target_journal") or "").strip()
    if target_journal and expected_journal and target_journal != expected_journal:
        raise ManuscriptCompletionError("Completion target_journal does not match the project journal.")
    revisions = payload.get("section_revisions", [])
    if not isinstance(revisions, list):
        raise ManuscriptCompletionError("section_revisions must be a list.")
    for index, revision in enumerate(revisions):
        if not isinstance(revision, dict):
            raise ManuscriptCompletionError(f"section_revisions[{index}] must be a mapping.")
    return {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": expected_project_id,
        "target_journal": target_journal,
        "metadata": _validate_metadata(payload.get("metadata")),
        "custom_references": _validate_references(payload.get("custom_references")),
        "section_revisions": [dict(item) for item in revisions],
    }


def _read_completion_input(path: str | Path) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ManuscriptCompletionError(f"Completion input does not exist: {source}")
    try:
        text = source.read_text(encoding="utf-8-sig")
        value = json.loads(text) if source.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ManuscriptCompletionError(f"Cannot parse completion input: {source}") from exc
    if not isinstance(value, dict):
        raise ManuscriptCompletionError("Completion input must be a YAML/JSON object.")
    return source, value


def resolve_manuscript_revision_target(project: str | Path, locator: dict[str, Any]) -> dict[str, Any]:
    """Expose completion locator diagnostics with completion-specific errors."""
    try:
        return _resolve_manuscript_revision_target(project, locator)
    except Exception as exc:
        from .manuscript_revision import ManuscriptRevisionError

        if isinstance(exc, ManuscriptRevisionError):
            raise ManuscriptCompletionError(str(exc)) from exc
        raise


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_revision(
    project: Path,
    input_dir: Path,
    raw: Any,
    index: int,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManuscriptCompletionError(f"section_revisions[{index}] must be a mapping.")
    allowed = {
        "revision_key",
        "target",
        "operation",
        "mode",
        "content",
        "content_file",
        "instruction",
        "change_class",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ManuscriptCompletionError(
            f"Unsupported section_revisions[{index}] fields: " + ", ".join(unknown)
        )
    revision_key = str(raw.get("revision_key") or "").strip()
    if not revision_key:
        raise ManuscriptCompletionError(f"section_revisions[{index}] requires revision_key.")
    target = raw.get("target")
    if not isinstance(target, dict):
        raise ManuscriptCompletionError(f"section_revisions[{index}].target must be a mapping.")
    operation = str(raw.get("operation") or "replace")
    if operation not in {"insert_before", "insert_after", "replace", "delete"}:
        raise ManuscriptCompletionError(f"section_revisions[{index}].operation is invalid.")
    mode = str(raw.get("mode") or "instruction_to_codex")
    if mode not in {"exact_text", "instruction_to_codex"}:
        raise ManuscriptCompletionError(f"section_revisions[{index}].mode is invalid.")
    if raw.get("content") is not None and raw.get("content_file") is not None:
        raise ManuscriptCompletionError(f"section_revisions[{index}] cannot use content and content_file together.")
    content = str(raw.get("content") or "")
    if raw.get("content_file") is not None:
        try:
            content_path = resolve_confined_path(input_dir, str(raw["content_file"]), must_exist=True)
        except BoundaryViolation as exc:
            raise ManuscriptCompletionError(
                f"section_revisions[{index}].content_file must stay inside the completion input directory."
            ) from exc
        content = content_path.read_text(encoding="utf-8-sig")
    instruction = str(raw.get("instruction") or "").strip()
    if mode == "exact_text" and operation != "delete" and not content:
        raise ManuscriptCompletionError(f"section_revisions[{index}] exact_text requires content.")
    if mode == "instruction_to_codex" and not instruction:
        raise ManuscriptCompletionError(f"section_revisions[{index}] instruction_to_codex requires instruction.")
    try:
        resolution = _resolve_manuscript_revision_target(project, target, refresh_source_map=False)
    except Exception as exc:
        from .manuscript_revision import ManuscriptRevisionError

        if isinstance(exc, ManuscriptRevisionError):
            raise ManuscriptCompletionError(str(exc)) from exc
        raise
    return {
        "revision_key": revision_key,
        "target": dict(target),
        "resolved_target": resolution,
        "operation": operation,
        "mode": mode,
        "content": content,
        "instruction": instruction,
        "change_class": raw.get("change_class"),
    }


def parse_manuscript_completion_packet(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    """Resolve one batch packet against one source-map and project revision without applying it."""
    state = load_project(project)
    source, raw = _read_completion_input(input_path)
    normalized = validate_manuscript_completion_payload(state.path, raw)
    build_manuscript_source_map(state.path)
    source_map_path = state.path / SOURCE_MAP
    source_map_sha256 = hashlib.sha256(source_map_path.read_bytes()).hexdigest()
    project_revision = int(load_project(state.path).metadata.get("state_revision") or 0)
    resolved = [
        _normalize_revision(state.path, source.parent, item, index)
        for index, item in enumerate(normalized["section_revisions"])
    ]
    revision_keys = [str(item["revision_key"]) for item in resolved]
    if len(revision_keys) != len(set(revision_keys)):
        raise ManuscriptCompletionError("duplicate_revision_key: revision_key values must be unique within a packet.")
    paragraph_ids = [str(item["resolved_target"].get("paragraph_id") or "") for item in resolved]
    duplicates = sorted({item for item in paragraph_ids if paragraph_ids.count(item) > 1})
    if duplicates:
        raise ManuscriptCompletionError(
            "conflicting_target: multiple revisions target the same paragraph: " + ", ".join(duplicates)
        )
    packet_core = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": normalized["project_id"],
        "target_journal": normalized["target_journal"],
        "project_revision": project_revision,
        "source_map_sha256": source_map_sha256,
        "metadata": normalized["metadata"],
        "custom_references": normalized["custom_references"],
        "resolved_revisions": resolved,
    }
    return {
        "status": "resolved",
        **packet_core,
        "packet_hash": _stable_hash(packet_core),
    }


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _merged_metadata(root: Path, supplied: dict[str, Any]) -> dict[str, Any]:
    existing = _read_yaml_mapping(root / "writing" / "manuscript_metadata.yaml")
    return {**existing, **supplied}


def _validate_abstract_boundary(root: Path, metadata: dict[str, Any]) -> None:
    abstract = str(metadata.get("abstract") or "").strip()
    registry = _read_json(root / "writing" / "scientific_evidence_registry.json")
    if not abstract or not registry:
        return
    report = validate_section_writing("abstract", abstract, registry)
    if report.get("decision") != "pass":
        detail = "; ".join(
            str(item.get("detail") or item.get("kind"))
            for item in report.get("issues") or []
            if isinstance(item, dict)
        )
        raise ManuscriptCompletionError("Abstract evidence contract failed: " + detail)


def _reference_identity(reference: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(reference.get("citation_key") or "").strip().lower(),
        str(reference.get("doi") or "").strip().lower().removeprefix("https://doi.org/"),
        re.sub(r"\W+", " ", str(reference.get("title") or "").lower()).strip(),
    )


def _existing_reference_index(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    items_path = root / "references" / "literature_items.json"
    try:
        items = json.loads(items_path.read_text(encoding="utf-8-sig")) if items_path.is_file() else []
    except json.JSONDecodeError:
        items = []
    by_key: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("bibtex_key") or item.get("citation_key") or "").strip().lower()
            if key:
                by_key[key] = item
    bib_path = root / "references" / "library.bib"
    return by_key, bib_path.read_text(encoding="utf-8-sig") if bib_path.is_file() else ""


def _validate_reference_candidates(root: Path, references: list[dict[str, Any]]) -> dict[str, Any]:
    existing_by_key, bib = _existing_reference_index(root)
    seen_keys: set[str] = set()
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    new_references: list[dict[str, Any]] = []
    already_present: list[str] = []
    for reference in references:
        key, doi, title = _reference_identity(reference)
        if key in seen_keys or (doi and doi in seen_dois) or (title and title in seen_titles):
            raise ManuscriptCompletionError(
                f"duplicate_reference: completion packet repeats {reference.get('citation_key')}."
            )
        seen_keys.add(key)
        if doi:
            seen_dois.add(doi)
        if title:
            seen_titles.add(title)
        existing = existing_by_key.get(key)
        bib_has_key = bool(re.search(rf"@[A-Za-z]+\{{\s*{re.escape(str(reference['citation_key']))}\s*,", bib))
        if existing or bib_has_key:
            existing_identity = _reference_identity(existing or reference)
            if existing and (doi and existing_identity[1] == doi or title and existing_identity[2] == title):
                already_present.append(str(reference["citation_key"]))
                continue
            if not existing and str(reference.get("evidence_only") or "").lower() in {"true", "1"}:
                already_present.append(str(reference["citation_key"]))
                continue
            raise ManuscriptCompletionError(
                f"duplicate_reference: citation key conflicts with an existing reference: {reference['citation_key']}"
            )
        new_references.append(reference)
    return {
        "count": len(references),
        "new_references": new_references,
        "already_present": already_present,
        "citation_keys": [str(item["citation_key"]) for item in references],
    }


def _bibtex_entry(reference: dict[str, Any]) -> str:
    entry_type = str(reference.get("entry_type") or ("article" if reference.get("journal") else "misc"))
    fields: list[tuple[str, Any]] = [
        ("author", " and ".join(str(item) for item in reference.get("authors") or [])),
        ("title", reference.get("title")),
        ("year", reference.get("year")),
        ("journal", reference.get("journal")),
        ("booktitle", reference.get("booktitle")),
        ("volume", reference.get("volume")),
        ("number", reference.get("issue")),
        ("pages", reference.get("pages")),
        ("publisher", reference.get("publisher")),
        ("doi", reference.get("doi")),
        ("url", reference.get("url") or (f"https://doi.org/{reference['doi']}" if reference.get("doi") else None)),
    ]
    rendered = [f"@{entry_type}{{{reference['citation_key']},"]
    rendered.extend(f"  {name} = {{{value}}}," for name, value in fields if value not in (None, ""))
    rendered.append("}")
    return "\n".join(rendered) + "\n"


def _candidate_sections(
    root: Path,
    resolved: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]], list[str]]:
    originals: dict[str, str] = {}
    proposed: dict[str, str] = {}
    classified: list[dict[str, Any]] = []
    unresolved: list[str] = []
    by_file: dict[str, list[dict[str, Any]]] = {}
    for revision in resolved:
        content = str(revision.get("content") or "")
        if revision.get("mode") == "instruction_to_codex" and not content:
            unresolved.append(str(revision["revision_key"]))
            continue
        target = dict(revision["resolved_target"])
        section = str(target.get("section") or "")
        change_class, stale_scope, citation_bearing = _classify(
            section,
            str(revision.get("instruction") or ""),
            content,
            str(revision.get("change_class") or "") or None,
        )
        row = {
            **revision,
            "change_class": change_class,
            "stale_scope": stale_scope,
            "citation_bearing": citation_bearing,
        }
        classified.append(row)
        by_file.setdefault(str(target["canonical_file"]), []).append(row)
    for canonical, revisions in by_file.items():
        source = root / canonical
        current = source.read_text(encoding="utf-8-sig")
        originals[canonical] = current
        for revision in sorted(
            revisions,
            key=lambda item: (
                int(item["resolved_target"].get("line_start") or 0),
                int(item["resolved_target"].get("line_end") or 0),
            ),
            reverse=True,
        ):
            target = revision["resolved_target"]
            current = _apply_operation(
                current,
                {"line_start": target["line_start"], "line_end": target["line_end"]},
                str(revision["operation"]),
                str(revision.get("content") or ""),
            )
        proposed[canonical] = current
    return originals, proposed, classified, unresolved


def _write_candidate_overlay(
    root: Path,
    packet_dir: Path,
    *,
    metadata: dict[str, Any],
    proposed_sections: dict[str, str],
    new_references: list[dict[str, Any]],
) -> Path:
    from .latex_assembly import _apply_manuscript_metadata, _render_main

    candidate_latex = packet_dir / "candidate" / "latex"
    sections_dir = candidate_latex / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    for section in ("introduction", "data", "methods", "results", "discussion", "result_artifacts"):
        canonical = root / section / f"{section}.tex"
        projection = root / "latex" / "sections" / f"{section}.tex"
        source = canonical if canonical.is_file() else projection
        if not source.is_file():
            continue
        relative = f"{section}/{section}.tex"
        text = proposed_sections.get(relative, source.read_text(encoding="utf-8-sig"))
        (sections_dir / f"{section}.tex").write_text(text, encoding="utf-8", newline="")
    main_source = root / "latex" / "main.tex"
    if main_source.is_file():
        main_text = main_source.read_text(encoding="utf-8-sig")
    else:
        main_text = _render_main(root, _read_json(root / "project.json"))
    journal = _read_json(root / "journal_profile" / "journal_profile.json")
    documentclass = str(journal.get("documentclass") or "").lower()
    main_text = _apply_manuscript_metadata(main_text, metadata, aastex="aastex" in documentclass)
    relative_root = os.path.relpath(root, candidate_latex).replace("\\", "/").rstrip("/") + "/"
    graphicspath = (
        "\\graphicspath{{"
        + relative_root
        + "}{"
        + relative_root
        + "results/figures/}{"
        + relative_root
        + "results/}}"
    )
    if "\\graphicspath" not in main_text:
        if not re.search(r"\\usepackage(?:\[[^]]*\])?\{graphicx\}", main_text):
            documentclass_match = re.search(r"\\documentclass(?:\[[^]]*\])?\{[^}]+\}", main_text)
            if documentclass_match:
                main_text = (
                    main_text[: documentclass_match.end()]
                    + "\n\\usepackage{graphicx}"
                    + main_text[documentclass_match.end() :]
                )
        main_text = main_text.replace("\\begin{document}", graphicspath + "\n\\begin{document}", 1)
    (candidate_latex / "main.tex").write_text(main_text, encoding="utf-8", newline="")
    bib_path = root / "latex" / "library.bib"
    if not bib_path.is_file():
        bib_path = root / "references" / "library.bib"
    bib = bib_path.read_text(encoding="utf-8-sig") if bib_path.is_file() else ""
    if bib and not bib.endswith("\n"):
        bib += "\n"
    bib += "\n".join(_bibtex_entry(item).rstrip() for item in new_references)
    if bib and not bib.endswith("\n"):
        bib += "\n"
    (candidate_latex / "library.bib").write_text(bib, encoding="utf-8", newline="")
    for directory in (root / "latex", root / "journal_profile", root / "latex" / "template"):
        if not directory.is_dir():
            continue
        for bst in directory.glob("*.bst"):
            shutil.copyfile(bst, candidate_latex / bst.name)
    return candidate_latex


def _build_completion_preview_pdf(
    root: Path,
    packet_dir: Path,
    *,
    candidate_latex: Path,
) -> dict[str, Any]:
    from .latex_assembly import _find_latex_executable

    engine = _find_latex_executable(["xelatex", "xelatex.exe", "pdflatex", "pdflatex.exe"])
    if not engine:
        return {
            "status": "compile_required",
            "pdf": None,
            "reason": "No local LaTeX engine is available for the candidate overlay.",
        }
    commands: list[dict[str, Any]] = []

    def run(command: list[str]) -> int:
        completed = subprocess.run(
            command,
            cwd=candidate_latex,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
            check=False,
        )
        commands.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
        return completed.returncode

    try:
        code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
        aux = candidate_latex / "main.aux"
        if code == 0 and aux.is_file() and "\\bibdata" in aux.read_text(encoding="utf-8", errors="ignore"):
            bibtex = _find_latex_executable(["bibtex", "bibtex.exe"])
            if bibtex:
                code = run([bibtex, "main"])
        if code == 0:
            code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
        if code == 0:
            code = run([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        commands.append({"error": str(exc)})
        code = 1
    compile_report = {
        "schema_version": "dpl.manuscript_completion_compile.v1",
        "status": "passed" if code == 0 else "failed",
        "engine": engine,
        "commands": commands,
    }
    _write_json(packet_dir / "preview_compile.json", compile_report)
    built = candidate_latex / "main.pdf"
    preview = packet_dir / "preview.pdf"
    if code == 0 and built.is_file():
        shutil.copyfile(built, preview)
        return {
            "status": "passed",
            "pdf": "preview.pdf",
            "engine": engine,
            "sha256": _file_sha256(preview),
            "compile_report": "preview_compile.json",
        }
    return {
        "status": "failed",
        "pdf": None,
        "engine": engine,
        "reason": "Candidate LaTeX compilation failed.",
        "compile_report": "preview_compile.json",
    }


def preview_manuscript_completion(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    """Build a non-canonical metadata/section/reference/PDF completion overlay."""
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    parsed = parse_manuscript_completion_packet(state.path, source)
    metadata = _merged_metadata(state.path, dict(parsed["metadata"]))
    _validate_abstract_boundary(state.path, metadata)
    missing = _missing_fields(state.path, metadata)
    reference_report = _validate_reference_candidates(
        state.path,
        [dict(item) for item in parsed["custom_references"]],
    )
    originals, proposed, classified, unresolved = _candidate_sections(
        state.path,
        [dict(item) for item in parsed["resolved_revisions"]],
    )
    scientific_reopen = [
        str(item["revision_key"])
        for item in classified
        if change_class_spec(str(item["change_class"])).reopen_evidence
        or change_class_spec(str(item["change_class"])).rerun_science
    ]
    try:
        snapshot = validate_promoted_snapshot_for_writing(state.path)
    except EvidenceSnapshotMismatch as exc:
        raise ManuscriptCompletionError(str(exc)) from exc
    packet_id = "packet:" + str(parsed["packet_hash"])[:16]
    packet_dir = state.path / PACKET_ROOT / packet_id.replace(":", "_")
    packet_dir.mkdir(parents=True, exist_ok=True)
    candidate_latex = _write_candidate_overlay(
        state.path,
        packet_dir,
        metadata=metadata,
        proposed_sections=proposed,
        new_references=[dict(item) for item in reference_report["new_references"]],
    )
    pdf_preview = _build_completion_preview_pdf(
        state.path,
        packet_dir,
        candidate_latex=candidate_latex,
    )
    preview_pdf = packet_dir / "preview.pdf"
    if preview_pdf.is_file() and not pdf_preview.get("sha256"):
        pdf_preview["sha256"] = _file_sha256(preview_pdf)

    diffs: list[str] = []
    before_metadata = _read_yaml_mapping(state.path / "writing" / "manuscript_metadata.yaml")
    before_metadata_text = yaml.safe_dump(before_metadata, allow_unicode=True, sort_keys=False)
    after_metadata_text = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    diffs.extend(
        difflib.unified_diff(
            before_metadata_text.splitlines(keepends=True),
            after_metadata_text.splitlines(keepends=True),
            fromfile="writing/manuscript_metadata.yaml",
            tofile="writing/manuscript_metadata.yaml (candidate)",
        )
    )
    for canonical, after in proposed.items():
        diffs.extend(
            difflib.unified_diff(
                originals[canonical].splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=canonical,
                tofile=canonical + " (candidate)",
            )
        )
    existing_bib_path = state.path / "references" / "library.bib"
    existing_bib = existing_bib_path.read_text(encoding="utf-8-sig") if existing_bib_path.is_file() else ""
    candidate_bib = (candidate_latex / "library.bib").read_text(encoding="utf-8-sig")
    diffs.extend(
        difflib.unified_diff(
            existing_bib.splitlines(keepends=True),
            candidate_bib.splitlines(keepends=True),
            fromfile="references/library.bib",
            tofile="references/library.bib (candidate)",
        )
    )

    if missing["missing_required"] or missing["placeholder_fields"]:
        decision = "missing_author_fields"
    elif unresolved:
        decision = "codex_patch_required"
    elif scientific_reopen:
        decision = "scientific_reopen_required"
    elif pdf_preview.get("status") != "passed":
        decision = str(pdf_preview.get("status") or "compile_required")
    else:
        decision = "pass"
    before_files = {
        canonical: _file_sha256(state.path / canonical)
        for canonical in originals
    }
    core = {
        "schema_version": "dpl.manuscript_completion_preview.v1",
        "project_id": parsed["project_id"],
        "target_journal": parsed["target_journal"],
        "project_revision": parsed["project_revision"],
        "source_map_sha256": parsed["source_map_sha256"],
        "evidence_snapshot_id": snapshot.get("snapshot_id"),
        "metadata_delta": parsed["metadata"],
        "merged_metadata": metadata,
        "custom_references": reference_report["new_references"],
        "already_present_references": reference_report["already_present"],
        "resolved_revisions": classified,
        "proposed_sections": proposed,
        "before_file_sha256": before_files,
        "unresolved_instruction_revisions": unresolved,
        "scientific_reopen_revisions": scientific_reopen,
        "pdf_preview": pdf_preview,
        "decision": decision,
    }
    packet_hash = _stable_hash(core)
    normalized = {
        "schema_version": "dpl.manuscript_completion_packet.v1",
        "packet_id": packet_id,
        "packet_hash": packet_hash,
        "core": core,
    }
    _write_json(packet_dir / "normalized_packet.json", normalized)
    atomic_write_text(packet_dir / "input.yaml", source.read_text(encoding="utf-8-sig"))
    _write_json(
        packet_dir / "missing_fields.json",
        {
            "schema_version": "dpl.manuscript_completion_missing.v1",
            "generated_at": utc_now(),
            **missing,
        },
    )
    _write_json(
        packet_dir / "locator_resolution.json",
        {
            "schema_version": "dpl.manuscript_completion_locator.v1",
            "generated_at": utc_now(),
            "source_map_sha256": parsed["source_map_sha256"],
            "project_revision": parsed["project_revision"],
            "resolutions": [item["resolved_target"] for item in classified],
            "unresolved_instruction_revisions": unresolved,
        },
    )
    change_report = {
        "schema_version": "dpl.manuscript_completion_change.v1",
        "changes": [
            {
                "revision_key": item["revision_key"],
                "change_class": item["change_class"],
                "stale_scope": item["stale_scope"],
                "citation_bearing": item["citation_bearing"],
            }
            for item in classified
        ],
        "scientific_reopen_revisions": scientific_reopen,
    }
    _write_json(packet_dir / "change_stale_report.json", change_report)
    validation = {
        "schema_version": "dpl.manuscript_completion_validation.v1",
        "generated_at": utc_now(),
        "packet_id": packet_id,
        "packet_hash": packet_hash,
        "decision": decision,
        "missing_fields": missing,
        "reference_report": {
            key: value for key, value in reference_report.items() if key != "new_references"
        },
        "resolved_revision_count": len(classified),
        "unresolved_instruction_revisions": unresolved,
        "scientific_reopen_revisions": scientific_reopen,
        "pdf_preview": pdf_preview,
    }
    _write_json(packet_dir / "validation_report.json", validation)
    atomic_write_text(packet_dir / "preview.diff", "".join(diffs))
    preview_lines = [
        "# Manuscript completion preview",
        "",
        f"Packet: `{packet_id}`",
        f"Packet hash: `{packet_hash}`",
        f"Decision: **{decision}**",
        "",
        f"Resolved revisions: {len(classified)}",
        f"New references: {len(reference_report['new_references'])}",
        f"Candidate PDF: {pdf_preview.get('status')}",
        "",
        "Review `preview.diff`, `change_stale_report.json`, and `preview.pdf` before applying.",
    ]
    atomic_write_text(packet_dir / "preview.md", "\n".join(preview_lines) + "\n")
    return {
        "status": "ready_for_human_review" if decision == "pass" else decision,
        "packet_id": packet_id,
        "packet_hash": packet_hash,
        "packet": _relative(packet_dir, state.path),
        "validation": _relative(packet_dir / "validation_report.json", state.path),
        "diff": _relative(packet_dir / "preview.diff", state.path),
        "preview_pdf": _relative(preview_pdf, state.path) if preview_pdf.is_file() else None,
        "resolved_revisions": len(classified),
        "next_command": (
            f'python -m draftpaper_cli.cli apply-manuscript-completion --project "{state.path}" '
            f'--packet-id "{packet_id}" --packet-hash "{packet_hash}"'
            if decision == "pass"
            else None
        ),
    }


def _completion_snapshot_patterns() -> tuple[str, ...]:
    return (
        "project.json",
        "project.yaml",
        "project_passport.yaml",
        "artifact_ledger.jsonl",
        "checkpoint_ledger.jsonl",
        "integrity_ledger.jsonl",
        "transaction_ledger.jsonl",
        "workflow_trace.jsonl",
        "*/stage_manifest.json",
        "stage_manifests/**",
        "writing/manuscript_metadata.yaml",
        "writing/user_locks.json",
        "writing/revision_ledger.jsonl",
        "writing/artifact_dependency_dag.json",
        "writing/artifact_stale_report.json",
        "references/**",
        "citation_audit/**",
        "introduction/introduction.tex",
        "data/data.tex",
        "methods/methods.tex",
        "results/results.tex",
        "discussion/discussion.tex",
        "latex/sections/**",
        "latex/library.bib",
        "latex/manuscript_source_map.json",
    )


def _matches_pattern(relative: str, patterns: tuple[str, ...]) -> bool:
    import fnmatch

    return any(
        fnmatch.fnmatchcase(relative, pattern)
        or fnmatch.fnmatchcase(relative, pattern.replace("/**", "/*"))
        for pattern in patterns
    )


def _snapshot_files(root: Path, patterns: tuple[str, ...], directory: Path) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = _relative(path, root)
        if not _matches_pattern(relative, patterns):
            continue
        content = path.read_bytes()
        token = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:20] + ".bin"
        atomic_write_bytes(directory / token, content)
        manifest[relative] = {
            "backup": token,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    _write_json(directory / "manifest.json", manifest)
    return manifest


def _restore_snapshot(root: Path, before_dir: Path, before: dict[str, Any], after: dict[str, Any]) -> None:
    for relative in sorted(set(after) - set(before), reverse=True):
        path = root / relative
        if path.is_file() and not path.is_symlink():
            path.unlink()
    for relative, item in before.items():
        if not isinstance(item, dict):
            continue
        backup = before_dir / str(item.get("backup") or "")
        if backup.is_file():
            atomic_write_bytes(root / relative, backup.read_bytes())


def _load_preview_packet(root: Path, packet_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    packet_dir = root / PACKET_ROOT / str(packet_id).replace(":", "_")
    normalized = _read_json(packet_dir / "normalized_packet.json")
    validation = _read_json(packet_dir / "validation_report.json")
    if not normalized or not isinstance(normalized.get("core"), dict):
        raise ManuscriptCompletionError(f"Completion packet does not exist: {packet_id}")
    return packet_dir, normalized, validation


def _validate_preview_still_current(root: Path, core: dict[str, Any]) -> None:
    state = load_project(root)
    if int(state.metadata.get("state_revision") or 0) != int(core.get("project_revision") or 0):
        raise ManuscriptCompletionError("Completion preview is stale because the project revision changed.")
    source_map = root / SOURCE_MAP
    if _file_sha256(source_map) != core.get("source_map_sha256"):
        raise ManuscriptCompletionError("Completion preview is stale because the manuscript source map changed.")
    try:
        snapshot = validate_promoted_snapshot_for_writing(root)
    except EvidenceSnapshotMismatch as exc:
        raise ManuscriptCompletionError(str(exc)) from exc
    if snapshot.get("snapshot_id") != core.get("evidence_snapshot_id"):
        raise ManuscriptCompletionError("Completion preview is stale because the promoted evidence snapshot changed.")
    for canonical, expected in (core.get("before_file_sha256") or {}).items():
        if _file_sha256(root / str(canonical)) != expected:
            raise ManuscriptCompletionError(f"Completion target changed after preview: {canonical}")


def _update_exact_user_locks(root: Path, packet_id: str, revisions: list[dict[str, Any]]) -> None:
    payload = _read_json(root / LOCKS_PATH)
    locks = [item for item in payload.get("locks") or [] if isinstance(item, dict)]
    revision_keys = {str(item.get("revision_key") or "") for item in revisions}
    locks = [item for item in locks if str(item.get("revision_key") or "") not in revision_keys]
    for revision in revisions:
        if revision.get("mode") != "exact_text":
            continue
        target = revision["resolved_target"]
        content = str(revision.get("content") or "")
        locks.append(
            {
                "packet_id": packet_id,
                "revision_key": revision["revision_key"],
                "paragraph_id": target.get("paragraph_id"),
                "section": target.get("section"),
                "exact_text_sha256": _sha_text(content),
                "active": True,
            }
        )
    _write_json(root / LOCKS_PATH, {"schema_version": "dpl.user_locks.v1", "locks": locks})


def apply_manuscript_completion(
    project: str | Path,
    packet_id: str,
    packet_hash: str,
) -> dict[str, Any]:
    """Apply one accepted completion preview as an idempotent bounded transaction."""
    state = load_project(project)
    packet_dir, normalized, validation = _load_preview_packet(state.path, packet_id)
    core = dict(normalized["core"])
    actual_hash = _stable_hash(core)
    if actual_hash != packet_hash or normalized.get("packet_hash") != packet_hash:
        raise ManuscriptCompletionError("Completion packet hash does not match the previewed packet hash.")
    receipt_path = packet_dir / "transaction_receipt.json"
    prior_receipt = _read_json(receipt_path)
    if prior_receipt.get("status") == "applied" and prior_receipt.get("packet_hash") == packet_hash:
        return {
            "status": "already_applied",
            "packet_id": packet_id,
            "packet_hash": packet_hash,
            "receipt": _relative(receipt_path, state.path),
        }
    if validation.get("decision") != "pass" or core.get("decision") != "pass":
        raise ManuscriptCompletionError("Only a ready completion packet can be applied.")
    _validate_preview_still_current(state.path, core)

    snapshot_patterns = _completion_snapshot_patterns()
    before_dir = packet_dir / "rollback" / "before"
    before_manifest = _snapshot_files(state.path, snapshot_patterns, before_dir)
    packet_relative = _relative(packet_dir, state.path)
    transaction_patterns = (
        *snapshot_patterns,
        ACTIVE_MANIFEST_PATH,
        COMPLETION_LEDGER_PATH,
        f"{packet_relative}/transaction_receipt.json",
        f"{packet_relative}/rollback/**",
    )
    with ScopedProjectTransaction(state.path, transaction_patterns) as transaction:
        metadata_delta = dict(core.get("metadata_delta") or {})
        if metadata_delta:
            metadata_file = packet_dir / "apply_metadata.yaml"
            atomic_write_text(
                metadata_file,
                yaml.safe_dump(metadata_delta, allow_unicode=True, sort_keys=False),
            )
            set_manuscript_metadata(state.path, metadata_file)
        references = [dict(item) for item in core.get("custom_references") or []]
        if references:
            references_file = packet_dir / "apply_references.json"
            atomic_write_text(
                references_file,
                json.dumps(references, ensure_ascii=False, indent=2) + "\n",
            )
            add_custom_reference(state.path, references_file)
        revisions = [dict(item) for item in core.get("resolved_revisions") or []]
        for canonical, text in (core.get("proposed_sections") or {}).items():
            atomic_write_text(state.path / str(canonical), str(text))
            section = next(
                (
                    str(item["resolved_target"].get("section") or "")
                    for item in revisions
                    if str(item["resolved_target"].get("canonical_file") or "") == str(canonical)
                ),
                "",
            )
            if section:
                atomic_write_text(state.path / "latex" / "sections" / f"{section}.tex", str(text))
        _update_exact_user_locks(state.path, packet_id, revisions)
        stale_reports: list[dict[str, Any]] = []
        for revision in revisions:
            target = revision["resolved_target"]
            canonical = str(target["canonical_file"])
            report = record_artifact_change(
                state.path,
                change_class=str(revision["change_class"]),
                source_artifact=canonical,
                source_hash=_file_sha256(state.path / canonical) or "",
                section=str(target.get("section") or ""),
            )
            stale_reports.append(report)
            append_jsonl_locked(
                state.path / REVISION_LEDGER,
                {
                    "schema_version": "dpl.revision_ledger.v1",
                    "event": "completion_applied",
                    "packet_id": packet_id,
                    "packet_hash": packet_hash,
                    "revision_key": revision["revision_key"],
                    "paragraph_id": target.get("paragraph_id"),
                    "change_class": revision["change_class"],
                    "recorded_at": utc_now(),
                },
            )
        active = {
            "schema_version": "dpl.active_manuscript_completion.v1",
            "status": "applied",
            "packet_id": packet_id,
            "packet_hash": packet_hash,
            "applied_at": utc_now(),
            "evidence_snapshot_id": core.get("evidence_snapshot_id"),
            "preview_pdf_sha256": (core.get("pdf_preview") or {}).get("sha256"),
            "metadata_fields": sorted(metadata_delta),
            "citation_keys": [str(item.get("citation_key")) for item in references],
            "revision_keys": [str(item.get("revision_key")) for item in revisions],
        }
        _write_json(state.path / ACTIVE_MANIFEST_PATH, active)
        append_jsonl_locked(
            state.path / COMPLETION_LEDGER_PATH,
            {
                "schema_version": "dpl.completion_ledger.v1",
                "event": "applied",
                "packet_id": packet_id,
                "packet_hash": packet_hash,
                "recorded_at": utc_now(),
            },
        )
        build_manuscript_source_map(state.path)
        after_dir = packet_dir / "rollback" / "after"
        after_manifest = _snapshot_files(state.path, snapshot_patterns, after_dir)
        receipt = {
            "schema_version": "dpl.manuscript_completion_receipt.v1",
            "status": "applied",
            "packet_id": packet_id,
            "packet_hash": packet_hash,
            "applied_at": utc_now(),
            "before_manifest": _relative(before_dir / "manifest.json", state.path),
            "after_manifest": _relative(after_dir / "manifest.json", state.path),
            "before_file_count": len(before_manifest),
            "after_file_count": len(after_manifest),
            "stale_reports": stale_reports,
        }
        _write_json(receipt_path, receipt)
        transaction.commit()
    return {
        "status": "applied",
        "packet_id": packet_id,
        "packet_hash": packet_hash,
        "receipt": _relative(receipt_path, state.path),
    }


def rollback_manuscript_completion(project: str | Path, transaction_id: str) -> dict[str, Any]:
    """Rollback a completion only while every affected after-hash remains current."""
    state = load_project(project)
    packet_dir, _normalized, _validation = _load_preview_packet(state.path, transaction_id)
    receipt_path = packet_dir / "transaction_receipt.json"
    receipt = _read_json(receipt_path)
    if receipt.get("status") == "rolled_back":
        return {"status": "already_rolled_back", "transaction_id": transaction_id}
    if receipt.get("status") != "applied":
        raise ManuscriptCompletionError(f"Completion receipt is not applied: {transaction_id}")
    before_manifest_path = state.path / str(receipt.get("before_manifest") or "")
    after_manifest_path = state.path / str(receipt.get("after_manifest") or "")
    before = _read_json(before_manifest_path)
    after = _read_json(after_manifest_path)
    if not before_manifest_path.is_file() or not after_manifest_path.is_file():
        raise ManuscriptCompletionError("Completion rollback snapshots are missing.")
    for relative, item in after.items():
        if not isinstance(item, dict):
            continue
        if _file_sha256(state.path / relative) != item.get("sha256"):
            raise ManuscriptCompletionError(
                f"Cannot rollback {transaction_id}: artifact changed after completion: {relative}"
            )
    snapshot_patterns = _completion_snapshot_patterns()
    packet_relative = _relative(packet_dir, state.path)
    transaction_patterns = (
        *snapshot_patterns,
        ACTIVE_MANIFEST_PATH,
        COMPLETION_LEDGER_PATH,
        f"{packet_relative}/transaction_receipt.json",
    )
    with ScopedProjectTransaction(state.path, transaction_patterns) as transaction:
        _restore_snapshot(state.path, before_manifest_path.parent, before, after)
        receipt["status"] = "rolled_back"
        receipt["rolled_back_at"] = utc_now()
        _write_json(receipt_path, receipt)
        active = _read_json(state.path / ACTIVE_MANIFEST_PATH)
        active.update(
            {
                "schema_version": "dpl.active_manuscript_completion.v1",
                "status": "rolled_back",
                "packet_id": transaction_id,
                "rolled_back_at": utc_now(),
            }
        )
        _write_json(state.path / ACTIVE_MANIFEST_PATH, active)
        append_jsonl_locked(
            state.path / COMPLETION_LEDGER_PATH,
            {
                "schema_version": "dpl.completion_ledger.v1",
                "event": "rolled_back",
                "packet_id": transaction_id,
                "recorded_at": utc_now(),
            },
        )
        transaction.commit()
    return {
        "status": "rolled_back",
        "transaction_id": transaction_id,
        "restored_file_count": len(before),
    }


def _journal_contract(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = _read_json(root / "journal_profile" / "journal_profile.json")
    raw_rules = profile.get("rules")
    rules: dict[str, Any] = dict(raw_rules) if isinstance(raw_rules, dict) else {}
    explicit = profile.get("completion_fields")
    nested_profile = profile.get("profile")
    if not isinstance(explicit, dict) and isinstance(nested_profile, dict):
        explicit = nested_profile.get("completion_fields")
    explicit = explicit if isinstance(explicit, dict) else {}
    required = [str(item) for item in explicit.get("required") or _DEFAULT_REQUIRED]
    if rules.get("requires_keywords") and "keywords" not in required:
        required.append("keywords")
    recommended = [str(item) for item in explicit.get("recommended") or _DEFAULT_RECOMMENDED]
    not_applicable = [str(item) for item in explicit.get("not_applicable") or []]
    allowed = _METADATA_FIELDS
    required = [item for item in required if item in allowed and item not in not_applicable]
    recommended = [item for item in recommended if item in allowed and item not in required and item not in not_applicable]
    return {
        "required": required,
        "recommended": recommended,
        "not_applicable": not_applicable,
    }, rules


def _missing_fields(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    contract, rules = _journal_contract(root)
    required = contract["required"]
    recommended = contract["recommended"]
    missing_required = [field for field in required if _is_empty(metadata.get(field))]
    missing_recommended = [field for field in recommended if _is_empty(metadata.get(field))]
    placeholders = _placeholder_fields(metadata)
    return {
        "required_fields": required,
        "recommended_fields": recommended,
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "placeholder_fields": placeholders,
        "not_applicable": contract["not_applicable"],
        "complete": not missing_required and not placeholders,
        "journal_rules": rules,
    }


def _template_payload(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    project = _read_json(root / "project.json")
    current = {field: metadata.get(field) for field in _METADATA_FIELDS if field in metadata}
    for field, default in (
        ("title", project.get("title")),
        ("short_title", None),
        ("abstract", None),
        ("keywords", []),
        ("authors", []),
        ("affiliations", []),
        ("acknowledgments", None),
    ):
        current.setdefault(field, default)
    return {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": project.get("project_id"),
        "target_journal": project.get("target_journal"),
        "metadata": current,
        "custom_references": [],
        "section_revisions": [],
    }


def prepare_manuscript_completion(project: str | Path) -> dict[str, Any]:
    """Write a user-editable completion template and journal missing-field report."""
    state = load_project(project)
    metadata = _read_yaml_mapping(state.path / "writing" / "manuscript_metadata.yaml")
    template = _template_payload(state.path, metadata)
    validate_manuscript_completion_payload(state.path, template)
    template_path = state.path / TEMPLATE_PATH
    atomic_write_text(template_path, yaml.safe_dump(template, allow_unicode=True, sort_keys=False))
    report = _missing_fields(state.path, metadata)
    report_path = state.path / MISSING_FIELDS_PATH
    _write_json(
        report_path,
        {
            "schema_version": "dpl.manuscript_completion_missing.v1",
            "generated_at": utc_now(),
            "project_id": state.metadata.get("project_id"),
            "target_journal": state.metadata.get("target_journal"),
            **report,
        },
    )
    return {
        "status": "template_written",
        "template": TEMPLATE_PATH,
        "missing_fields": MISSING_FIELDS_PATH,
        "missing_required": report["missing_required"],
        "placeholder_fields": report["placeholder_fields"],
        "next_command": f'python -m draftpaper_cli.cli manuscript-completion-status --project "{state.path}"',
    }


def manuscript_completion_status(project: str | Path) -> dict[str, Any]:
    """Report final-author completion readiness without mutating project state."""
    state = load_project(project)
    metadata = _read_yaml_mapping(state.path / "writing" / "manuscript_metadata.yaml")
    report = _missing_fields(state.path, metadata)
    template_exists = (state.path / TEMPLATE_PATH).is_file()
    active = _read_json(state.path / ACTIVE_MANIFEST_PATH)
    packets: list[dict[str, Any]] = []
    packets_root = state.path / PACKET_ROOT
    if packets_root.is_dir():
        for validation_path in sorted(packets_root.glob("packet_*/validation_report.json")):
            validation = _read_json(validation_path)
            packets.append(
                {
                    "packet_id": validation.get("packet_id"),
                    "packet_hash": validation.get("packet_hash"),
                    "decision": validation.get("decision"),
                    "path": _relative(validation_path.parent, state.path),
                }
            )
    if active:
        status = str(active.get("status") or "unknown")
    elif not template_exists:
        status = "not_prepared"
    elif report["complete"]:
        status = "ready_for_preview"
    else:
        status = "needs_author_input"
    return {
        "schema_version": "dpl.manuscript_completion_status.v1",
        "status": status,
        "project_id": state.metadata.get("project_id"),
        "target_journal": state.metadata.get("target_journal"),
        "template": TEMPLATE_PATH,
        "template_exists": template_exists,
        "active_completion_manifest": ACTIVE_MANIFEST_PATH if active else None,
        "active": active,
        "packet_count": len(packets),
        "packets": packets,
        **report,
        "next_command": (
            f'python -m draftpaper_cli.cli prepare-manuscript-completion --project "{state.path}"'
            if not template_exists
            else None
        ),
    }


__all__ = [
    "COMPLETION_SCHEMA",
    "ManuscriptCompletionError",
    "apply_manuscript_completion",
    "manuscript_completion_status",
    "parse_manuscript_completion_packet",
    "prepare_manuscript_completion",
    "preview_manuscript_completion",
    "resolve_manuscript_revision_target",
    "rollback_manuscript_completion",
    "validate_manuscript_completion_payload",
]
