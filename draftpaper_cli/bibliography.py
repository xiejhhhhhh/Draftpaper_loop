"""Structured reference registry, version decisions, and bibliography validation."""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import bibtexparser

from .project_scaffold import utc_now
from .project_state import load_project


REFERENCE_REGISTRY = "references/reference_registry.json"
BIBLIOGRAPHY_CONTRACT = "references/bibliography_contract.json"
DUPLICATE_REPORT = "references/reference_duplicate_report.json"
SUPPLEMENTAL_BIBLIOGRAPHY = "references/supplemental_library.bib"
SUPPLEMENTAL_MERGE_REPORT = "references/supplemental_bibliography_merge_report.json"
VERSION_DECISIONS = "references/reference_version_decisions.json"
BIBLIOGRAPHY_REPORT = "quality_checks/bibliography_quality_report.json"
REFERENCE_PROOF = "quality_checks/reference_proof.html"


class BibliographyError(RuntimeError):
    """Raised when bibliography metadata or version decisions are unsafe."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _doi(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    return text.strip().rstrip(".,").lower()


def _arxiv(value: Any, url: Any = "") -> str:
    text = f"{value or ''} {url or ''}"
    match = re.search(r"(?:arxiv:|arxiv\.org/(?:abs|pdf)/)([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", text, flags=re.I)
    return match.group(1) if match else ""


def _plain_title(value: Any) -> str:
    text = re.sub(r"[{}]", "", str(value or ""))
    text = re.sub(r"\\[A-Za-z]+\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _plain_title(value).lower())


def _protect_title(value: Any) -> str:
    title = str(value or "").strip()
    if not title:
        return ""
    parts = re.split(r"(\s+)", title)
    protected = []
    for part in parts:
        if not part or part.isspace() or (part.startswith("{") and part.endswith("}")):
            protected.append(part)
            continue
        core = part.strip(".,:;()[]")
        uppercase = sum(char.isupper() for char in core)
        internal_capital = any(char.isupper() for char in core[1:])
        needs = uppercase >= 2 or (any(char.isdigit() for char in core) and internal_capital) or ("-" in core and uppercase >= 1)
        protected.append(part.replace(core, "{" + core + "}", 1) if core and needs else part)
    return "".join(protected)


def _split_authors(value: Any) -> list[dict[str, str]]:
    text = str(value or "").strip()
    if not text:
        return []
    authors = re.split(r"\s+and\s+", text)
    result = []
    for author in authors:
        cleaned = author.strip()
        if not cleaned:
            continue
        if "," in cleaned:
            family, given = [item.strip() for item in cleaned.split(",", 1)]
        else:
            parts = cleaned.split()
            family, given = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (cleaned, "")
        result.append({"family": family, "given": given, "literal": cleaned})
    return result


def _canonical_url(fields: dict[str, Any], doi: str, arxiv_id: str) -> str:
    if doi:
        return f"https://doi.org/{doi}"
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    raw = str(fields.get("url") or "").strip()
    if raw.startswith("http://"):
        raw = "https://" + raw[len("http://"):]
    host = urlparse(raw).netloc.lower()
    if "semanticscholar.org" in host:
        return ""
    return raw


def _work_type(entry_type: str, fields: dict[str, Any], arxiv_id: str) -> str:
    if arxiv_id and not fields.get("volume") and not fields.get("pages") and not fields.get("number"):
        return "preprint"
    if entry_type in {"inproceedings", "conference"}:
        return "conference"
    if entry_type in {"dataset", "data"}:
        return "dataset"
    if entry_type == "article":
        return "journal_article"
    return entry_type or "misc"


def _bib_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or not path.read_text(encoding="utf-8-sig").strip():
        return []
    try:
        database = bibtexparser.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise BibliographyError(f"Structured BibTeX parsing failed: {exc}") from exc
    return [dict(item) for item in database.entries]


def materialize_effective_bibliography(project: str | Path) -> tuple[str, dict[str, Any]]:
    """Merge the curated and optional supplemental BibTeX sources without hiding conflicts."""
    root = Path(project)
    primary_path = root / "references" / "library.bib"
    supplemental_path = root / SUPPLEMENTAL_BIBLIOGRAPHY
    primary = _bib_entries(primary_path)
    supplemental = _bib_entries(supplemental_path)
    merged = list(primary)
    by_key = {str(item.get("ID") or ""): item for item in primary}
    by_doi = {_doi(item.get("doi")): item for item in primary if _doi(item.get("doi"))}
    accepted: list[str] = []
    skipped: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []

    for entry in supplemental:
        key = str(entry.get("ID") or "").strip()
        doi = _doi(entry.get("doi"))
        title_id = _title_identity(entry.get("title"))
        existing_key = by_key.get(key)
        if not key:
            conflicts.append({"citation_key": "", "reason": "missing_citation_key"})
            continue
        if existing_key is not None:
            same_work = bool(
                (doi and doi == _doi(existing_key.get("doi")))
                or (title_id and title_id == _title_identity(existing_key.get("title")))
            )
            if same_work:
                skipped.append({"citation_key": key, "reason": "duplicate_citation_key_same_work"})
            else:
                conflicts.append({"citation_key": key, "reason": "citation_key_conflict"})
            continue
        if doi and doi in by_doi:
            conflicts.append({
                "citation_key": key,
                "reason": "duplicate_doi_with_different_citation_key",
                "existing_citation_key": str(by_doi[doi].get("ID") or ""),
            })
            continue
        merged.append(entry)
        by_key[key] = entry
        if doi:
            by_doi[doi] = entry
        accepted.append(key)

    report = {
        "schema_version": "dpl.supplemental_bibliography_merge_report.v1",
        "generated_at": utc_now(),
        "status": "failed" if conflicts else "passed",
        "primary_source": "references/library.bib",
        "supplemental_source": SUPPLEMENTAL_BIBLIOGRAPHY if supplemental_path.is_file() else None,
        "primary_record_count": len(primary),
        "supplemental_record_count": len(supplemental),
        "effective_record_count": len(merged),
        "accepted_supplemental_keys": accepted,
        "skipped_duplicates": skipped,
        "conflicts": conflicts,
        "policy": "Supplemental records are explicit project evidence; citation-key or DOI conflicts must be resolved rather than silently overwritten.",
    }
    _write_json(root / SUPPLEMENTAL_MERGE_REPORT, report)
    if conflicts:
        labels = ", ".join(item.get("citation_key") or "<missing>" for item in conflicts)
        raise BibliographyError(f"Supplemental bibliography conflicts require resolution: {labels}")
    database = bibtexparser.bibdatabase.BibDatabase()
    database.entries = merged
    return bibtexparser.dumps(database), report


def _literature_index(root: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(root / "references" / "literature_items.json")
    rows = payload if isinstance(payload, list) else payload.get("items") or [] if isinstance(payload, dict) else []
    return {
        str(item.get("bibtex_key") or item.get("citation_key")): dict(item)
        for item in rows
        if isinstance(item, dict) and (item.get("bibtex_key") or item.get("citation_key"))
    }


def _bst_record(root: Path, style: str) -> dict[str, Any]:
    candidates = list((root / "latex" / "template").glob(f"{style}.bst")) + list((root / "journal_profile").glob(f"{style}.bst"))
    path = candidates[0] if candidates else None
    if path is None and shutil.which("kpsewhich"):
        completed = subprocess.run(["kpsewhich", f"{style}.bst"], capture_output=True, text=True, timeout=10)
        candidate = Path(completed.stdout.strip()) if completed.returncode == 0 and completed.stdout.strip() else None
        path = candidate if candidate and candidate.is_file() else None
    return {
        "style": style,
        "source": str(path) if path else "tex_distribution_or_unresolved",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path else None,
    }


def build_reference_registry(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    bib_path = state.path / "references" / "library.bib"
    effective_bibtex, merge_report = materialize_effective_bibliography(state.path)
    effective_database = bibtexparser.loads(effective_bibtex)
    supplemental_keys = set(merge_report.get("accepted_supplemental_keys") or [])
    literature = _literature_index(state.path)
    records = []
    for entry in effective_database.entries:
        key = str(entry.get("ID") or "")
        source = literature.get(key, {})
        doi = _doi(entry.get("doi") or source.get("doi"))
        arxiv_id = _arxiv(entry.get("eprint") or source.get("arxiv_id"), entry.get("url") or source.get("url"))
        title_original = _plain_title(entry.get("title") or source.get("title"))
        canonical_id = f"doi:{doi}" if doi else f"arxiv:{re.sub(r'v[0-9]+$', '', arxiv_id)}" if arxiv_id else f"title:{hashlib.sha256(_title_identity(title_original).encode()).hexdigest()[:20]}"
        work_type = _work_type(str(entry.get("ENTRYTYPE") or "misc").lower(), entry, arxiv_id)
        record = {
            "canonical_work_id": canonical_id,
            "citation_key": key,
            "entry_type": str(entry.get("ENTRYTYPE") or "misc").lower(),
            "work_type": work_type,
            "structured_authors": _split_authors(entry.get("author") or " and ".join(source.get("authors") or [])),
            "title_original": title_original,
            "title_bibtex_protected": _protect_title(entry.get("title") or title_original),
            "year": str(entry.get("year") or source.get("year") or ""),
            "journal": str(entry.get("journal") or source.get("publication") or ""),
            "volume": str(entry.get("volume") or ""),
            "issue": str(entry.get("number") or entry.get("issue") or ""),
            "pages_or_article_number": str(entry.get("pages") or entry.get("eid") or entry.get("article-number") or ""),
            "publisher": str(entry.get("publisher") or ""),
            "doi_normalized": doi,
            "canonical_url": _canonical_url(entry, doi, arxiv_id),
            "arxiv_id": arxiv_id,
            "eprint": arxiv_id if work_type == "preprint" else str(entry.get("eprint") or ""),
            "archive_prefix": "arXiv" if arxiv_id else str(entry.get("archiveprefix") or ""),
            "primary_class": str(entry.get("primaryclass") or source.get("primary_class") or ""),
            "publication_status": "published" if work_type == "journal_article" else "preprint" if work_type == "preprint" else "other",
            "related_versions": [],
            "preferred_citable_version": None,
            "metadata_sources": sorted(set(
                ["library.bib"]
                + (["supplemental_library.bib"] if key in supplemental_keys else [])
                + ([str(source.get("source") or "literature_items")] if source else [])
            )),
            "field_confidence": {"title": "source", "doi": "source" if doi else "missing", "authors": "source"},
            "user_confirmed": False,
            "raw_extra_fields": {
                name: value
                for name, value in entry.items()
                if name.lower() not in {"id", "entrytype", "title", "author", "year", "journal", "volume", "number", "issue", "pages", "eid", "article-number", "publisher", "doi", "url", "eprint", "archiveprefix", "primaryclass"}
            },
        }
        records.append(record)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(record["canonical_work_id"], []).append(record)
    by_title: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_title.setdefault(_title_identity(record["title_original"]), []).append(record)
    for same_title in by_title.values():
        if len(same_title) > 1:
            canonical = next((item["canonical_work_id"] for item in same_title if item["doi_normalized"]), same_title[0]["canonical_work_id"])
            for item in same_title:
                item["canonical_work_id"] = canonical
    groups = {}
    for record in records:
        groups.setdefault(record["canonical_work_id"], []).append(record)
    for same_work in groups.values():
        keys = [item["citation_key"] for item in same_work]
        for item in same_work:
            item["related_versions"] = [key for key in keys if key != item["citation_key"]]
    profile = _read_json(state.path / "journal_profile" / "journal_profile.json")
    style = str(profile.get("bibliography_style") or "plainnat") if isinstance(profile, dict) else "plainnat"
    contract = {
        "schema_version": "dpl.bibliography_contract.v1",
        "generated_at": utc_now(),
        "target_journal": state.metadata.get("target_journal"),
        "document_class": profile.get("documentclass") if isinstance(profile, dict) else None,
        "bibliography_style": style,
        "bst": _bst_record(state.path, style),
        "engine": "BibTeX",
        "required_fields": {
            "journal_article": ["structured_authors", "title_original", "year", "journal"],
            "preprint": ["structured_authors", "title_original", "year", "eprint", "archive_prefix"],
            "conference": ["structured_authors", "title_original", "year"],
            "dataset": ["title_original", "year", "publisher", "canonical_url"],
        },
        "publication_locator_policy": {
            "journal_article_any_of": ["doi_normalized", "pages_or_article_number", "canonical_url", "eprint"],
            "reason": "Continuous-publication journals may not assign traditional volume or page fields.",
        },
        "doi_url_policy": "Store bare lowercase DOI and canonical HTTPS URL; reject aggregator URLs when a DOI exists.",
        "preprint_policy": "Published version is suggested but never selected without an explicit version decision.",
        "title_capitalization_policy": "Protect acronyms, identifiers, mixed-case names and hyphenated proper terms with BibTeX braces.",
        "duplicate_version_policy": "Do not render multiple versions of one work until the preferred citable version is confirmed.",
        "hyperlink_policy": "HTML reports link DOI and canonical URL; PDF follows the journal bst.",
    }
    registry = {
        "schema_version": "dpl.reference_registry.v1",
        "status": "needs_version_confirmation" if any(len(items) > 1 for items in groups.values()) else "ready",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "source_bibtex_sha256": hashlib.sha256(effective_bibtex.encode("utf-8")).hexdigest(),
        "supplemental_merge_report": SUPPLEMENTAL_MERGE_REPORT,
        "record_count": len(records),
        "records": records,
    }
    _write_json(state.path / REFERENCE_REGISTRY, registry)
    _write_json(state.path / BIBLIOGRAPHY_CONTRACT, contract)
    inspect_reference_duplicates(state.path)
    return {"status": "written", "record_count": len(records), "registry": REFERENCE_REGISTRY, "contract": BIBLIOGRAPHY_CONTRACT, "version_confirmation_required": registry["status"] != "ready"}


def inspect_reference_duplicates(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    registry = _read_json(state.path / REFERENCE_REGISTRY)
    if not registry:
        raise BibliographyError("Build the reference registry before duplicate inspection.")
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in registry.get("records") or []:
        if isinstance(item, dict):
            groups.setdefault(str(item.get("canonical_work_id")), []).append(item)
    duplicates = []
    for work_id, items in groups.items():
        if len(items) < 2:
            continue
        preferred = [item for item in items if item.get("preferred_citable_version") is True and item.get("user_confirmed")]
        published = [item for item in items if item.get("publication_status") == "published"]
        suggestion = published[0]["citation_key"] if published else items[0]["citation_key"]
        duplicates.append({
            "canonical_work_id": work_id,
            "citation_keys": [item.get("citation_key") for item in items],
            "suggested_preferred_key": suggestion,
            "status": "resolved" if len(preferred) == 1 else "user_confirmation_required",
            "preferred_key": preferred[0]["citation_key"] if len(preferred) == 1 else None,
            "reason": "published_version_preferred" if published else "duplicate_or_related_versions",
        })
    report = {
        "schema_version": "dpl.reference_duplicate_report.v1",
        "status": "confirmation_required" if any(item["status"] != "resolved" for item in duplicates) else "passed",
        "generated_at": utc_now(),
        "duplicate_work_count": sum(item["status"] != "resolved" for item in duplicates),
        "duplicate_works": duplicates,
        "policy": "Suggestions never alter retained references without an explicit pre-writing version decision.",
    }
    _write_json(state.path / DUPLICATE_REPORT, report)
    return report


def _author_bibtex(authors: list[dict[str, Any]]) -> str:
    return " and ".join(
        f"{item.get('family')}, {item.get('given')}".rstrip(", ")
        for item in authors
        if item.get("family") or item.get("literal")
    )


def _render_registry_bib(records: list[dict[str, Any]]) -> str:
    entries = []
    for record in records:
        fields = {
            "author": _author_bibtex(record.get("structured_authors") or []),
            "title": record.get("title_bibtex_protected"),
            "year": record.get("year"),
            "journal": record.get("journal") if record.get("work_type") == "journal_article" else "",
            "volume": record.get("volume"),
            "number": record.get("issue"),
            "pages": record.get("pages_or_article_number"),
            "publisher": record.get("publisher"),
            "doi": record.get("doi_normalized"),
            "url": record.get("canonical_url"),
            "eprint": record.get("eprint"),
            "archivePrefix": record.get("archive_prefix"),
            "primaryClass": record.get("primary_class"),
            **dict(record.get("raw_extra_fields") or {}),
        }
        lines = [f"  {name} = {{{value}}}" for name, value in fields.items() if value not in (None, "")]
        entries.append(f"@{record.get('entry_type') or 'misc'}{{{record['citation_key']},\n" + ",\n".join(lines) + "\n}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def resolve_reference_version(project: str | Path, work: str, preferred_key: str) -> dict[str, Any]:
    state = load_project(project)
    registry = _read_json(state.path / REFERENCE_REGISTRY)
    records = [item for item in registry.get("records") or [] if isinstance(item, dict)]
    group = [item for item in records if item.get("canonical_work_id") == work]
    if len(group) < 2:
        raise BibliographyError(f"Canonical work is not an unresolved multi-version group: {work}")
    if preferred_key not in {str(item.get("citation_key")) for item in group}:
        raise BibliographyError("Preferred key is not a member of the canonical work group.")
    section_text = "\n".join(
        path.read_text(encoding="utf-8-sig", errors="replace")
        for path in (state.path / "latex" / "sections").glob("*.tex")
    )
    nonpreferred = [str(item.get("citation_key")) for item in group if item.get("citation_key") != preferred_key]
    cited_nonpreferred = [key for key in nonpreferred if re.search(rf"\\cite\w*\{{[^}}]*\b{re.escape(key)}\b", section_text)]
    if cited_nonpreferred:
        raise BibliographyError("Version resolution must occur before writing or through an explicit citation revision; cited keys: " + ", ".join(cited_nonpreferred))
    for item in group:
        item["preferred_citable_version"] = item.get("citation_key") == preferred_key
        item["user_confirmed"] = True
    decisions = _read_json(state.path / VERSION_DECISIONS)
    rows = [item for item in decisions.get("decisions") or [] if isinstance(item, dict) and item.get("canonical_work_id") != work]
    rows.append({"canonical_work_id": work, "preferred_key": preferred_key, "excluded_related_keys": nonpreferred, "confirmed_at": utc_now()})
    _write_json(state.path / VERSION_DECISIONS, {"schema_version": "dpl.reference_version_decisions.v1", "decisions": rows})
    registry["records"] = records
    unresolved = inspect_reference_duplicates_from_records(records, resolved_work_ids={str(item["canonical_work_id"]) for item in rows})
    registry["status"] = "ready" if not unresolved else "needs_version_confirmation"
    _write_json(state.path / REFERENCE_REGISTRY, registry)
    rendered = [
        item for item in records
        if not item.get("related_versions") or item.get("preferred_citable_version") is True
    ]
    (state.path / "references" / "library.bib").write_text(_render_registry_bib(rendered), encoding="utf-8")
    inspect_reference_duplicates(state.path)
    return {"status": "resolved", "canonical_work_id": work, "preferred_key": preferred_key, "rendered_reference_count": len(rendered)}


def inspect_reference_duplicates_from_records(records: list[dict[str, Any]], resolved_work_ids: set[str]) -> list[str]:
    groups: dict[str, int] = {}
    for item in records:
        groups[str(item.get("canonical_work_id"))] = groups.get(str(item.get("canonical_work_id")), 0) + 1
    return [work_id for work_id, count in groups.items() if count > 1 and work_id not in resolved_work_ids]


def _main_styles(text: str) -> list[str]:
    return re.findall(r"\\bibliographystyle\{([^}]+)\}", text)


def validate_bibliography(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    registry = _read_json(state.path / REFERENCE_REGISTRY)
    contract = _read_json(state.path / BIBLIOGRAPHY_CONTRACT)
    if not registry or not contract:
        build_reference_registry(state.path)
        registry = _read_json(state.path / REFERENCE_REGISTRY)
        contract = _read_json(state.path / BIBLIOGRAPHY_CONTRACT)
    issues = []
    required_by_type = contract.get("required_fields") or {}
    for record in registry.get("records") or []:
        if not isinstance(record, dict):
            continue
        for field in required_by_type.get(record.get("work_type"), []):
            if record.get(field) in (None, "", []):
                issues.append({"severity": "error", "kind": "missing_required_field", "citation_key": record.get("citation_key"), "field": field})
        if record.get("work_type") == "journal_article":
            locator_fields = (
                (contract.get("publication_locator_policy") or {}).get("journal_article_any_of")
                or ["doi_normalized", "pages_or_article_number", "canonical_url", "eprint"]
            )
            if not any(record.get(field) not in (None, "", []) for field in locator_fields):
                issues.append({
                    "severity": "error",
                    "kind": "missing_publication_locator",
                    "citation_key": record.get("citation_key"),
                    "fields": list(locator_fields),
                })
        doi = str(record.get("doi_normalized") or "")
        if doi.startswith(("http://", "https://", "doi:")):
            issues.append({"severity": "error", "kind": "doi_not_normalized", "citation_key": record.get("citation_key")})
        url = str(record.get("canonical_url") or "")
        if url and not url.startswith("https://"):
            issues.append({"severity": "error", "kind": "noncanonical_url", "citation_key": record.get("citation_key")})
    duplicate_report = inspect_reference_duplicates(state.path)
    if duplicate_report.get("status") != "passed":
        issues.append({"severity": "error", "kind": "unresolved_reference_versions", "count": duplicate_report.get("duplicate_work_count")})
    style = str(contract.get("bibliography_style") or "")
    main_tex = (state.path / "latex" / "main.tex").read_text(encoding="utf-8-sig", errors="replace") if (state.path / "latex" / "main.tex").is_file() else ""
    main_styles = _main_styles(main_tex)
    if main_tex and main_styles != [style]:
        issues.append({"severity": "error", "kind": "bibliography_style_mismatch", "expected": style, "observed": main_styles})
    aux_text = (state.path / "latex" / "main.aux").read_text(encoding="utf-8-sig", errors="replace") if (state.path / "latex" / "main.aux").is_file() else ""
    aux_styles = re.findall(r"\\bibstyle\{([^}]+)\}", aux_text)
    if aux_styles and aux_styles != [style]:
        issues.append({"severity": "error", "kind": "aux_bibliography_style_mismatch", "expected": style, "observed": aux_styles})
    compile_manifest = _read_json(state.path / "latex" / "pdf_compile_manifest.json")
    warnings = []
    log_path = state.path / "latex" / "main.blg"
    if log_path.is_file():
        warnings = [line.strip() for line in log_path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if "warning" in line.lower()]
    report = {
        "schema_version": "dpl.bibliography_quality_report.v1",
        "status": "passed" if not [item for item in issues if item.get("severity") == "error"] else "failed",
        "generated_at": utc_now(),
        "record_count": registry.get("record_count"),
        "bibliography_style": style,
        "main_tex_styles": main_styles,
        "aux_styles": aux_styles,
        "bbl_present": (state.path / "latex" / "main.bbl").is_file(),
        "compile_manifest_status": compile_manifest.get("status") if isinstance(compile_manifest, dict) else None,
        "bibtex_warnings": warnings,
        "issues": issues,
        "citation_support_audit": "separate: citation_audit/final_citation_audit_report.json",
    }
    _write_json(state.path / BIBLIOGRAPHY_REPORT, report)
    return report


def render_reference_proof(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    registry = _read_json(state.path / REFERENCE_REGISTRY)
    report = validate_bibliography(state.path)
    rows = []
    for item in registry.get("records") or []:
        doi = str(item.get("doi_normalized") or "")
        url = str(item.get("canonical_url") or "")
        doi_html = f'<a href="https://doi.org/{html.escape(doi)}">{html.escape(doi)}</a>' if doi else ""
        url_html = f'<a href="{html.escape(url)}">source</a>' if url else ""
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('citation_key') or ''))}</td>"
            f"<td>{html.escape(str(item.get('title_original') or ''))}</td>"
            f"<td>{html.escape(str(item.get('publication_status') or ''))}</td>"
            f"<td>{doi_html}</td><td>{url_html}</td>"
            f"<td>{html.escape(str(item.get('preferred_citable_version')))}</td>"
            "</tr>"
        )
    page = """<!doctype html><html><head><meta charset="utf-8"><title>Reference Proof</title>
<style>body{font-family:system-ui,sans-serif;margin:2rem;color:#17202a}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd1d1;padding:.45rem;text-align:left;vertical-align:top}th{background:#eef2f3}.failed{color:#a21b1b}.passed{color:#176b3a}</style></head><body>"""
    page += f"<h1>Reference Proof</h1><p class=\"{report['status']}\">Bibliography format audit: {report['status']}</p>"
    page += "<table><thead><tr><th>Key</th><th>Title</th><th>Status</th><th>DOI</th><th>URL</th><th>Preferred</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></body></html>"
    target = state.path / REFERENCE_PROOF
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return {"status": "written", "quality_status": report["status"], "proof": REFERENCE_PROOF, "record_count": len(rows)}
