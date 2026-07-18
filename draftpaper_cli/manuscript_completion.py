"""Structured final-author completion packets and journal missing-field reports."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from .project_scaffold import utc_now
from .project_state import load_project
from .manuscript_revision import (
    SOURCE_MAP,
    build_manuscript_source_map,
    resolve_manuscript_revision_target as _resolve_manuscript_revision_target,
)
from .state_kernel import atomic_write_text
from .write_set_guard import BoundaryViolation, resolve_confined_path


COMPLETION_ROOT = "writing/manuscript_completion"
TEMPLATE_PATH = f"{COMPLETION_ROOT}/template.yaml"
MISSING_FIELDS_PATH = f"{COMPLETION_ROOT}/missing_fields.json"
ACTIVE_MANIFEST_PATH = f"{COMPLETION_ROOT}/active_completion_manifest.json"
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
    if active:
        status = "applied"
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
    "manuscript_completion_status",
    "parse_manuscript_completion_packet",
    "prepare_manuscript_completion",
    "resolve_manuscript_revision_target",
    "validate_manuscript_completion_payload",
]
