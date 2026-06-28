# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import re
import unicodedata


DPL_LOOP_EVENTS = [
    "project_initialized",
    "project_state_observed",
    "next_safe_stage_decided",
    "evidence_loaded",
    "evidence_bound",
    "claim_trace_built",
    "discipline_constraints_loaded",
    "manuscript_projected",
    "artifact_hash_recorded",
    "downstream_stage_marked_stale",
    "gate_failure_diagnosed",
    "revision_routed",
    "revision_closed",
]

DPL_ERROR_PREFIXES = {
    "project": "DPL-PROJ",
    "evidence": "DPL-EVID",
    "claim": "DPL-CLAM",
    "loop": "DPL-LOOP",
    "discipline": "DPL-DISC",
    "manuscript": "DPL-MANU",
}


def normalize_contract_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def slugify_contract(value: str) -> str:
    normalized = normalize_contract_text(value)
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "unspecified"


def _short_hash(*parts: str) -> str:
    normalized = "\n".join(normalize_contract_text(part) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:6]


def stable_claim_id(section: str, claim_text: str, *, sequence: int = 1) -> str:
    section_slug = slugify_contract(section)
    return f"clm_{section_slug}_{sequence:04d}_{_short_hash(section_slug, claim_text)}"


def _normalize_doi(doi: str) -> str:
    normalized = normalize_contract_text(doi)
    normalized = re.sub(r"^(https? )?doi org ", "", normalized)
    return normalized.replace(" ", ".")


def stable_evidence_id(
    source_type: str,
    *,
    doi: str = "",
    title: str = "",
    first_author: str = "",
    year: str = "",
    sequence: int = 1,
) -> str:
    source_slug = slugify_contract(source_type)
    identity = _normalize_doi(doi) if doi else " ".join([title, first_author, year])
    return f"evd_{source_slug}_{sequence:04d}_{_short_hash(source_slug, identity)}"
