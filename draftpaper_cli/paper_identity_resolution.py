"""Hash-bound identity resolution for shortlisted literature candidates."""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from ._vendor.paper_fetch_skill.provenance import PAPER_FETCH_VERSION, UPSTREAM_COMMIT
from .literature_fetch_policy import default_literature_fetch_policy, validate_literature_fetch_policy
from .literature_identity import canonical_work_id
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


IDENTITY_SCHEMA = "dpl.paper_identity_resolution.v1"
IDENTITY_JSONL = "references/paper_identity_resolutions.jsonl"
IDENTITY_SUMMARY = "references/paper_identity_resolution_summary.json"
UNRESOLVED_IDENTITIES = "references/unresolved_paper_identities.json"

IdentityResolver = Callable[[dict[str, Any]], dict[str, Any]]


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _identity_input(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "doi": _normalize_doi(item.get("doi")),
        "title": str(item.get("title") or ""),
        "authors": list(item.get("authors") or []),
        "year": str(item.get("year") or ""),
        "url": str(item.get("url") or ""),
    }


def _normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().casefold()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = doi.removeprefix("doi:").strip()
    return doi.rstrip(".,;)")


def _normalize_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", str(value or "").casefold()).strip()


def _title_similarity(left: Any, right: Any) -> float | None:
    left_value = _normalize_title(left)
    right_value = _normalize_title(right)
    if not left_value or not right_value:
        return None
    sequence = SequenceMatcher(None, left_value, right_value).ratio()
    left_tokens = set(left_value.split())
    right_tokens = set(right_value.split())
    jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return round(max(sequence, jaccard), 4)


def _author_tokens(values: Any) -> set[str]:
    authors = values if isinstance(values, list) else [values] if values else []
    result: set[str] = set()
    for author in authors:
        normalized = _normalize_title(author)
        if normalized:
            result.add(normalized)
            result.add(normalized.split()[-1])
    return result


def _author_overlap(left: Any, right: Any) -> float | None:
    left_values = _author_tokens(left)
    right_values = _author_tokens(right)
    if not left_values or not right_values:
        return None
    return round(len(left_values & right_values) / max(1, min(len(left_values), len(right_values))), 4)


def _year_delta(left: Any, right: Any) -> int | None:
    left_match = re.search(r"(?:19|20)\d{2}", str(left or ""))
    right_match = re.search(r"(?:19|20)\d{2}", str(right or ""))
    if not left_match or not right_match:
        return None
    return abs(int(left_match.group(0)) - int(right_match.group(0)))


def _direct_resolution(item: dict[str, Any]) -> dict[str, Any] | None:
    doi = _normalize_doi(item.get("doi"))
    if doi:
        return {
            "doi": doi,
            "title": item.get("title"),
            "authors": item.get("authors") or [],
            "year": item.get("year"),
            "provider": item.get("source_provider") or item.get("source") or "input_metadata",
            "confidence": 1.0,
            "resolution_basis": "normalized_doi",
            "independently_resolved_fields": ["doi"],
        }
    for field in ("pmid", "pmcid", "arxiv_id", "bibcode", "openalex_id"):
        value = str(item.get(field) or "").strip()
        if value:
            return {
                field: value,
                "title": item.get("title"),
                "authors": item.get("authors") or [],
                "year": item.get("year"),
                "provider": item.get("source_provider") or item.get("source") or "input_metadata",
                "confidence": 1.0,
                "resolution_basis": f"normalized_{field}",
                "independently_resolved_fields": [field],
            }
    url = str(item.get("url") or "")
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", url, flags=re.IGNORECASE)
    if match:
        return {
            "doi": _normalize_doi(match.group(0)),
            "title": item.get("title"),
            "authors": item.get("authors") or [],
            "year": item.get("year"),
            "landing_url": url,
            "provider": item.get("source_provider") or item.get("source") or "input_url",
            "confidence": 1.0,
            "resolution_basis": "doi_from_url",
            "independently_resolved_fields": ["doi", "landing_url"],
        }
    curated = bool(
        item.get("retained")
        or item.get("user_confirmed")
        or item.get("reference_origin") in {"existing_zotero", "local_import", "manual", "parent_lineage_curated"}
    )
    if curated and item.get("title") and item.get("authors") and item.get("year"):
        return {
            "title": item.get("title"),
            "authors": item.get("authors") or [],
            "year": item.get("year"),
            "provider": item.get("source_provider") or item.get("source") or "curated_input",
            "confidence": 0.9,
            "resolution_basis": "curated_title_author_year",
            "independently_resolved_fields": ["title", "authors", "year"],
        }
    return None


def _vendored_title_resolution(item: dict[str, Any]) -> dict[str, Any]:
    from ._vendor.paper_fetch_skill.paper_fetch.workflow.resolution import resolve_paper

    resolved = resolve_paper(str(item.get("title") or ""))
    payload = resolved.to_dict()
    return {
        "doi": payload.get("doi"),
        "title": payload.get("title"),
        "authors": [],
        "year": None,
        "landing_url": payload.get("landing_url"),
        "provider": payload.get("provider_hint") or "paper_fetch",
        "confidence": payload.get("confidence") or 0.0,
        "candidates": payload.get("candidates") or [],
        "resolution_basis": "paper_fetch_title_resolution",
        "independently_resolved_fields": [field for field in ("doi", "title", "landing_url") if payload.get(field)],
    }


def _resolution_status(item: dict[str, Any], resolved: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    input_doi = _normalize_doi(item.get("doi"))
    resolved_doi = _normalize_doi(resolved.get("doi"))
    doi_match = input_doi == resolved_doi if input_doi and resolved_doi else None
    title_similarity = _title_similarity(item.get("title"), resolved.get("title"))
    author_overlap = _author_overlap(item.get("authors"), resolved.get("authors"))
    year_delta = _year_delta(item.get("year"), resolved.get("year"))
    checks = {
        "doi_match": doi_match,
        "title_similarity": title_similarity,
        "author_overlap": author_overlap,
        "year_delta": year_delta,
        "independently_resolved_fields": list(resolved.get("independently_resolved_fields") or []),
    }
    reasons: list[str] = []
    upstream_status = str(resolved.get("status") or "")
    if upstream_status in {"no_access", "provider_degraded", "rate_limited"}:
        return upstream_status, checks, [upstream_status]
    if resolved.get("candidates"):
        return "ambiguous", checks, ["multiple_resolution_candidates"]
    if doi_match is False:
        reasons.append("doi_mismatch")
    if title_similarity is not None and title_similarity < 0.72:
        reasons.append("title_mismatch")
    if author_overlap is not None and author_overlap == 0:
        reasons.append("author_mismatch")
    if year_delta is not None and year_delta > 1:
        reasons.append("year_mismatch")
    if reasons:
        return "mismatch", checks, reasons
    if doi_match is True or resolved.get("resolution_basis", "").startswith("normalized_"):
        return "resolved_exact", checks, ["stable_identifier_exact"]
    if title_similarity is not None and title_similarity >= 0.9 and float(resolved.get("confidence") or 0.0) >= 0.9:
        return "resolved_probable", checks, ["high_confidence_title_resolution"]
    return "unresolved", checks, ["insufficient_identity_evidence"]


def resolve_candidate_identity(
    item: dict[str, Any],
    *,
    resolver: IdentityResolver | None = None,
    allow_network: bool = False,
    candidate_set_hash: str = "",
    query_contract_hash: str = "",
    policy_hash: str = "",
) -> dict[str, Any]:
    input_payload = _identity_input(item)
    candidate_id = canonical_work_id(item) or "candidate:" + _canonical_hash(input_payload).removeprefix("sha256:")[:20]
    try:
        resolved = resolver(dict(item)) if resolver else _direct_resolution(item)
        if resolved is None and allow_network and item.get("title"):
            resolved = _vendored_title_resolution(item)
        if resolved is None:
            resolved = {"status": "unresolved", "resolution_basis": "no_stable_identifier"}
    except Exception as exc:  # provider failure is a per-candidate degraded state
        resolved = {
            "status": "provider_degraded",
            "resolution_basis": "paper_fetch_resolution_error",
            "error_type": type(exc).__name__,
        }
    status, checks, reasons = _resolution_status(item, resolved)
    resolved_payload = {
        "work_id": canonical_work_id({**item, **{key: value for key, value in resolved.items() if value}}),
        "doi": _normalize_doi(resolved.get("doi")),
        "title": str(resolved.get("title") or ""),
        "authors": list(resolved.get("authors") or []),
        "year": str(resolved.get("year") or ""),
        "landing_url": str(resolved.get("landing_url") or ""),
        "provider": str(resolved.get("provider") or ""),
        "confidence": float(resolved.get("confidence") or 0.0),
        "resolution_basis": str(resolved.get("resolution_basis") or ""),
        "candidates": list(resolved.get("candidates") or []),
    }
    return {
        "schema_version": IDENTITY_SCHEMA,
        "candidate_id": candidate_id,
        "input": input_payload,
        "resolved": resolved_payload,
        "status": status,
        "reason_codes": reasons,
        "checks": checks,
        "input_hash": _canonical_hash(input_payload),
        "candidate_set_hash": candidate_set_hash,
        "query_contract_hash": query_contract_hash,
        "policy_hash": policy_hash,
        "runtime_source": "vendored_paper_fetch_adapter",
        "runtime_version": PAPER_FETCH_VERSION,
        "runtime_upstream_commit": UPSTREAM_COMMIT,
        "generated_at": utc_now(),
    }


def revalidate_identity_after_fetch(item: dict[str, Any]) -> dict[str, Any]:
    """Re-check the original candidate identity against fetched metadata."""
    value = dict(item)
    metadata = value.get("paper_fetch_resolved_metadata")
    if not isinstance(metadata, dict) or not metadata:
        return value
    resolved = {
        **metadata,
        "confidence": 1.0,
        "resolution_basis": "paper_fetch_resolved_metadata",
        "independently_resolved_fields": [key for key, item_value in metadata.items() if item_value],
    }
    status, checks, reasons = _resolution_status(value, resolved)
    previous_status = str(value.get("identity_resolution_status") or "unresolved")
    if status in {"mismatch", "ambiguous"} or previous_status not in {"resolved_exact", "resolved_probable"}:
        value["identity_resolution_status"] = status
    value["postfetch_identity_validation"] = {
        "schema_version": IDENTITY_SCHEMA,
        "status": status,
        "previous_status": previous_status,
        "checks": checks,
        "reason_codes": reasons,
        "resolved_metadata_hash": _canonical_hash(metadata),
        "generated_at": utc_now(),
    }
    return value


def resolve_literature_identities(
    project: str | Path,
    items: list[dict[str, Any]],
    *,
    query_contract: dict[str, Any] | None = None,
    fetch_policy: dict[str, Any] | None = None,
    resolver: IdentityResolver | None = None,
    allow_network: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state = load_project(project)
    policy = validate_literature_fetch_policy(fetch_policy or default_literature_fetch_policy())
    contract = dict(query_contract or {})
    candidate_set_hash = _canonical_hash(items)
    query_contract_hash = _canonical_hash(contract)
    maximum = int(policy.get("max_identity_candidates") or 0)
    cached_receipts: dict[str, dict[str, Any]] = {}
    cache_path = state.path / IDENTITY_JSONL
    if cache_path.is_file():
        for line in cache_path.read_text(encoding="utf-8-sig").splitlines():
            try:
                cached = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(cached, dict):
                continue
            input_hash = str(cached.get("input_hash") or "")
            stable = cached.get("status") in {"resolved_exact", "resolved_probable", "ambiguous", "mismatch"}
            same_runtime = str(cached.get("runtime_upstream_commit") or "") == UPSTREAM_COMMIT
            if input_hash and stable and same_runtime:
                cached_receipts[input_hash] = cached
    receipts: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        item = dict(raw)
        input_hash = _canonical_hash(_identity_input(item))
        cached = cached_receipts.get(input_hash)
        if cached:
            receipt = {
                **cached,
                "candidate_set_hash": candidate_set_hash,
                "query_contract_hash": query_contract_hash,
                "policy_hash": policy.get("policy_hash"),
                "cache_hit": True,
            }
        elif index >= maximum:
            receipt = resolve_candidate_identity(
                item,
                candidate_set_hash=candidate_set_hash,
                query_contract_hash=query_contract_hash,
                policy_hash=str(policy.get("policy_hash") or ""),
            )
            receipt = {**receipt, "status": "unresolved", "reason_codes": ["identity_candidate_limit_exceeded"]}
            receipt["cache_hit"] = False
        else:
            receipt = resolve_candidate_identity(
                item,
                resolver=resolver,
                allow_network=allow_network,
                candidate_set_hash=candidate_set_hash,
                query_contract_hash=query_contract_hash,
                policy_hash=str(policy.get("policy_hash") or ""),
            )
            receipt["cache_hit"] = False
        receipts.append(receipt)
        resolved = receipt.get("resolved") if isinstance(receipt.get("resolved"), dict) else {}
        if not item.get("doi") and receipt["status"] in {"resolved_exact", "resolved_probable"} and resolved.get("doi"):
            item["doi"] = resolved["doi"]
        item["identity_resolution_status"] = receipt["status"]
        item["identity_resolution_receipt"] = receipt
        item["resolved_work_id"] = resolved.get("work_id") or canonical_work_id(item)
        enriched.append(item)

    references_dir = state.path / "references"
    references_dir.mkdir(parents=True, exist_ok=True)
    (state.path / IDENTITY_JSONL).write_text(
        "\n".join(json.dumps(receipt, ensure_ascii=False, sort_keys=True) for receipt in receipts) + ("\n" if receipts else ""),
        encoding="utf-8",
    )
    status_counts: dict[str, int] = {}
    for receipt in receipts:
        status = str(receipt.get("status") or "unresolved")
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = {
        "schema_version": "dpl.paper_identity_resolution_summary.v1",
        "status": "completed" if receipts else "empty",
        "candidate_count": len(items),
        "resolved_count": sum(status_counts.get(value, 0) for value in ("resolved_exact", "resolved_probable")),
        "status_counts": status_counts,
        "candidate_set_hash": candidate_set_hash,
        "query_contract_hash": query_contract_hash,
        "policy_hash": policy.get("policy_hash"),
        "runtime_source": "vendored_paper_fetch_adapter",
        "runtime_version": PAPER_FETCH_VERSION,
        "runtime_upstream_commit": UPSTREAM_COMMIT,
        "generated_at": utc_now(),
        "receipts": IDENTITY_JSONL,
    }
    _write_json(state.path / IDENTITY_SUMMARY, summary)
    unresolved = [receipt for receipt in receipts if receipt.get("status") not in {"resolved_exact", "resolved_probable"}]
    _write_json(
        state.path / UNRESOLVED_IDENTITIES,
        {
            "schema_version": "dpl.unresolved_paper_identities.v1",
            "candidate_set_hash": candidate_set_hash,
            "count": len(unresolved),
            "items": unresolved,
        },
    )
    return enriched, summary
