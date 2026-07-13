# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .citation_utils import bibtex_keys_in_text
from .project_scaffold import _write_json, utc_now


CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}",
    re.IGNORECASE,
)

SECTION_PRIORITY = ["data", "methods", "discussion", "introduction"]
CITATION_ROLES = {
    "dataset_provenance",
    "instrument_or_product_definition",
    "processing_method_support",
    "method_or_tool_background",
    "prior_result_comparison",
    "mechanism_or_interpretation",
    "general_background",
}


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def _read_evidence(project_path: Path) -> list[dict[str, str]]:
    path = project_path / "references" / "citation_evidence.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _library_keys(project_path: Path) -> set[str]:
    path = project_path / "references" / "library.bib"
    if not path.exists():
        return set()
    return bibtex_keys_in_text(path.read_text(encoding="utf-8-sig", errors="ignore"))


def _key_for_item(item: dict[str, Any]) -> str:
    return str(item.get("bibtex_key") or item.get("citation_key") or "").strip()


def _clean_text(text: Any, limit: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _target_section(rows: list[dict[str, str]]) -> str:
    sections = {str(row.get("section") or "").strip().lower() for row in rows}
    for section in SECTION_PRIORITY:
        if section in sections:
            return section
    return "introduction"


def _citation_role(section: str, rows: list[dict[str, str]], item: dict[str, Any]) -> tuple[str, str]:
    for row in rows:
        declared = str(row.get("citation_role") or row.get("citation_intent") or "").strip().lower()
        if declared in CITATION_ROLES:
            return declared, "citation_evidence_contract"
    blob = " ".join(
        [
            section,
            str(item.get("title") or ""),
            str(item.get("abstract") or ""),
            " ".join(str(row.get("claim") or "") + " " + str(row.get("evidence_summary") or "") for row in rows),
        ]
    ).lower()
    if section == "data":
        if any(term in blob for term in ["instrument", "telescope", "detector", "product definition", "response matrix"]):
            return "instrument_or_product_definition", "registry_section_assignment"
        if any(term in blob for term in ["processing", "calibration", "normalization", "pipeline", "preprocessing"]):
            return "processing_method_support", "registry_section_assignment"
        return "dataset_provenance", "registry_section_assignment"
    if section == "methods":
        return "method_or_tool_background", "registry_section_assignment"
    if section == "discussion":
        if any(term in blob for term in ["mechanism", "interpret", "explain", "physical", "biological"]):
            return "mechanism_or_interpretation", "registry_section_assignment"
        return "prior_result_comparison", "registry_section_assignment"
    return "general_background", "registry_section_assignment"


def _best_evidence(rows: list[dict[str, str]], item: dict[str, Any]) -> str:
    for row in rows:
        evidence = _clean_text(row.get("evidence_summary") or row.get("claim"))
        if evidence:
            return evidence
    return _clean_text(item.get("abstract") or item.get("title") or "This retained reference provides relevant context.")


def _best_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[0] if rows else {}


def build_reference_usage_plan(project: str | Path) -> dict[str, Any]:
    """Create a required citation-use plan from retained literature summaries."""
    project_path = Path(project)
    references_dir = project_path / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    literature_items = _read_json(references_dir / "literature_items.json", [])
    if not isinstance(literature_items, list):
        literature_items = []
    bib_keys = _library_keys(project_path)
    evidence_rows = _read_evidence(project_path)
    evidence_by_key: dict[str, list[dict[str, str]]] = {}
    for row in evidence_rows:
        key = str(row.get("citation_key") or "").strip()
        if key:
            evidence_by_key.setdefault(key, []).append(row)

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in literature_items:
        if not isinstance(item, dict):
            continue
        key = _key_for_item(item)
        if not key or key in seen:
            continue
        if bib_keys and key not in bib_keys:
            continue
        seen.add(key)
        rows = evidence_by_key.get(key) or []
        target = _target_section(rows)
        row = _best_row(rows)
        citation_role, role_source = _citation_role(target, rows, item)
        entries.append(
            {
                "citation_key": key,
                "required": True,
                "target_section": target,
                "citation_role": citation_role,
                "citation_intent": citation_role,
                "role_assignment_source": role_source,
                "claim_scope": _clean_text(row.get("claim") or item.get("title") or "background evidence"),
                "evidence_summary": _best_evidence(rows, item),
                "source": row.get("source") or item.get("source") or "",
                "doi": row.get("doi") or item.get("doi") or "",
                "url": row.get("url") or item.get("url") or "",
                "title": _clean_text(item.get("title") or key, 220),
            }
        )

    plan = {
        "status": "written",
        "generated_at": utc_now(),
        "policy": "Every retained reference in references/literature_summaries must be cited at least once outside Results.",
        "citation_role_contract_version": "dpl.citation_role.v2",
        "source_literature_keys": sorted(seen),
        "source_bibtex_keys": sorted(bib_keys),
        "total_required_references": len(entries),
        "entries": entries,
    }
    _write_json(references_dir / "reference_usage_plan.json", plan)
    return plan


def ensure_reference_usage_plan(project: str | Path) -> dict[str, Any]:
    project_path = Path(project)
    path = project_path / "references" / "reference_usage_plan.json"
    payload = _read_json(path, {})
    literature_items = _read_json(project_path / "references" / "literature_items.json", [])
    current_literature_keys = sorted(
        key
        for key in (_key_for_item(item) for item in literature_items if isinstance(item, dict))
        if key
    ) if isinstance(literature_items, list) else []
    current_bib_keys = sorted(_library_keys(project_path))
    planned_literature_keys = sorted(str(item) for item in payload.get("source_literature_keys") or []) if isinstance(payload, dict) else []
    planned_bib_keys = sorted(str(item) for item in payload.get("source_bibtex_keys") or []) if isinstance(payload, dict) else []
    if (
        isinstance(payload, dict)
        and payload.get("entries")
        and planned_literature_keys == current_literature_keys
        and planned_bib_keys == current_bib_keys
    ):
        return payload
    return build_reference_usage_plan(project_path)


def citation_keys_in_text(text: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION_PATTERN.finditer(text or ""):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def entries_for_section(project: str | Path, section: str) -> list[dict[str, Any]]:
    project_path = Path(project)
    plan = ensure_reference_usage_plan(project)
    bib_keys = _library_keys(project_path)
    target = section.strip().lower()
    return [
        entry
        for entry in plan.get("entries") or []
        if entry.get("required") and str(entry.get("target_section") or "").strip().lower() == target
        and (not bib_keys or str(entry.get("citation_key") or "") in bib_keys)
    ]


def missing_entries_for_section(project: str | Path, section: str, existing_text: str) -> list[dict[str, Any]]:
    cited = citation_keys_in_text(existing_text)
    return [entry for entry in entries_for_section(project, section) if str(entry.get("citation_key") or "") not in cited]
