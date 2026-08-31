"""Canonical, confirmed literature corpus for downstream teaching extensions.

The research workflow contains many literature-adjacent artifacts: search
queries, rejected candidates, provider reports, cache manifests and rendered
HTML.  They are useful for audit, but none of them is a paper admission
decision.  This module exports the small, explicit corpus that extensions such
as Draftpaper_learn are allowed to consume.

The contract deliberately has no dependency on the Guidance runtime.  Core
creates it from its own registry/usage-plan contracts; extensions can then
verify the hash instead of re-discovering papers by walking ``references/``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TEACHING_CORPUS_SCHEMA = "dpl.literature_teaching_corpus.v1"
TEACHING_CORPUS_PATH = "references/literature_teaching_corpus_manifest.json"
# These values describe a derived projection rather than the scientific
# literature set the user reviewed.  In particular, a reference-index rebuild
# rewrites its snapshot marker and the hash of the generated ``library.bib``.
# Treating either as an admission input would invalidate a still-identical
# confirmed corpus every time its HTML/index projection is refreshed.
_VOLATILE_DOCUMENT_KEYS = frozenset(
    {
        "created_at",
        "generated_at",
        "rendered_at",
        "updated_at",
        "written_at",
        "snapshot_hash",
        "_snapshot_hash",
        "source_bibtex_sha256",
    }
)


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback


def _sha256_path(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _stable_document_value(value: Any) -> Any:
    """Remove generated timestamps before hashing a JSON source artifact."""

    if isinstance(value, Mapping):
        return {str(key): _stable_document_value(item) for key, item in value.items() if str(key) not in _VOLATILE_DOCUMENT_KEYS}
    if isinstance(value, list):
        return [_stable_document_value(item) for item in value]
    return value


def _semantic_sha256_path(path: Path) -> str | None:
    payload = _read_json(path, None)
    if payload is None:
        return _sha256_path(path)
    return _canonical_hash(_stable_document_value(payload))


def _canonical_hash(value: Mapping[str, Any]) -> str:
    material = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _corpus_identity_work(value: Mapping[str, Any]) -> dict[str, Any]:
    """Exclude derived display links from the scientific corpus identity hash."""

    return {str(key): item for key, item in value.items() if str(key) not in {"summary_detail_path"}}


def _items(document: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(document, Mapping):
        for key in keys:
            value = document.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(document, list):
        return [dict(item) for item in document if isinstance(item, Mapping)]
    return []


def _active_literature_path(references: Path) -> Path | None:
    """Return the explicit active snapshot, never a candidate/rejection file."""

    exact = references / "active_literature.json"
    if exact.is_file():
        return exact
    candidates = sorted(references.glob("active_literature_*.json"))
    return candidates[-1] if candidates else None


def _artifact_ref(root: Path, path: Path, kind: str) -> dict[str, str] | None:
    digest = _semantic_sha256_path(path)
    if digest is None:
        return None
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": digest,
        "kind": kind,
    }


def _summary_detail_path(index: int, citation_key: str) -> str:
    """Return the deterministic summary path used by the Core HTML projection."""

    stem = re.sub(r"[^A-Za-z0-9]+", "_", citation_key).strip("_").lower()[:70]
    return f"references/literature_summaries/{index:02d}_{stem or 'paper'}.html"


def literature_confirmation_binding(project: str | Path) -> dict[str, Any]:
    """Return the hash-bound scientific set a user is being asked to confirm."""

    root = Path(project).expanduser().resolve()
    references = root / "references"
    registry_path = references / "reference_registry.json"
    usage_path = references / "reference_usage_plan.json"
    active_path = _active_literature_path(references)
    registry = _read_json(registry_path, {})
    usage = _read_json(usage_path, {})
    active = _read_json(active_path, {}) if active_path is not None else {}
    registry_keys = {
        str(record.get("citation_key") or "").strip()
        for record in _items(registry, "records")
        if str(record.get("citation_key") or "").strip()
        and str(record.get("canonical_work_id") or "").strip()
    }
    usage_keys = {
        str(item.get("citation_key") or item.get("bibtex_key") or "").strip()
        for item in _items(usage, "entries")
        if str(item.get("citation_key") or item.get("bibtex_key") or "").strip()
    }
    active_keys = {
        str(item.get("bibtex_key") or item.get("citation_key") or "").strip()
        for item in _items(active, "items", "records")
        if str(item.get("bibtex_key") or item.get("citation_key") or "").strip()
    }
    return {
        "schema_version": "dpl.literature_confirmation_binding.v1",
        "project_id": str(registry.get("project_id") or ""),
        "reference_registry_sha256": _semantic_sha256_path(registry_path),
        "reference_usage_plan_sha256": _semantic_sha256_path(usage_path),
        "active_literature_path": active_path.relative_to(root).as_posix() if active_path else None,
        "active_literature_sha256": _semantic_sha256_path(active_path) if active_path else None,
        "registry_citation_keys": sorted(registry_keys),
        "active_citation_keys": sorted(active_keys),
        "usage_plan_citation_keys": sorted(usage_keys),
        "accepted_citation_keys": sorted(registry_keys & usage_keys & active_keys),
    }


def literature_confirmation_packet_hash(document: Mapping[str, Any]) -> str:
    """Hash the review packet without trusting a self-declared hash field."""

    return _canonical_hash({str(key): value for key, value in document.items() if str(key) != "packet_hash"})


def _binding_without_derived_registry_projection(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the user-reviewed admission decision separate from index outputs."""

    return {
        key: binding.get(key)
        for key in (
            "schema_version",
            "project_id",
            "reference_usage_plan_sha256",
            "active_literature_path",
            "active_literature_sha256",
            "registry_citation_keys",
            "active_citation_keys",
            "usage_plan_citation_keys",
            "accepted_citation_keys",
        )
    }


def _packet_work_identities(packet: Mapping[str, Any]) -> tuple[tuple[str, str], ...] | None:
    """Read the canonical work identities that the user actually reviewed."""

    candidates = packet.get("confirmed_corpus_candidates")
    if not isinstance(candidates, list):
        return None
    identities = {
        (
            str(item.get("citation_key") or "").strip(),
            str(item.get("canonical_work_id") or "").strip(),
        )
        for item in candidates
        if isinstance(item, Mapping)
        and str(item.get("citation_key") or "").strip()
        and str(item.get("canonical_work_id") or "").strip()
    }
    return tuple(sorted(identities)) if identities else None


def _current_work_identities(references: Path, binding: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return current canonical identities for the confirmed citation keys."""

    registry = _read_json(references / "reference_registry.json", {})
    accepted = {
        str(value).strip()
        for value in binding.get("accepted_citation_keys") or ()
        if str(value).strip()
    }
    identities = {
        (
            str(record.get("citation_key") or "").strip(),
            str(record.get("canonical_work_id") or "").strip(),
        )
        for record in _items(registry, "records")
        if str(record.get("citation_key") or "").strip() in accepted
        and str(record.get("canonical_work_id") or "").strip()
    }
    return tuple(sorted(identities))


def _is_equivalent_confirmation_after_derived_rebuild(
    packet: Mapping[str, Any],
    stored_binding: Mapping[str, Any],
    current_binding: Mapping[str, Any],
    references: Path,
) -> bool:
    """Recognize a prior decision when only an index projection was rebuilt.

    Older receipts included the registry's derived snapshot/BibTeX hashes.  A
    rebuild could therefore change that one digest even though the reviewed
    accepted keys, active source, usage-plan roles, and canonical work IDs
    stayed unchanged.  Continuity is intentionally narrow: any change to the
    active source, usage plan, membership, or canonical identity still needs a
    fresh human confirmation.
    """

    if _binding_without_derived_registry_projection(stored_binding) != _binding_without_derived_registry_projection(current_binding):
        return False
    reviewed = _packet_work_identities(packet)
    return reviewed is not None and reviewed == _current_work_identities(references, current_binding)


def _confirmation_receipt(
    references: Path,
    binding: Mapping[str, Any],
) -> tuple[str | None, str]:
    """Find the explicit human confirmation required for teaching publication.

    A legacy active snapshot can still help build an operational candidate
    index, but it never upgrades a set of papers into a confirmed teaching
    corpus.  This keeps old search artifacts from becoming learner evidence
    merely because their registry and usage-plan records happen to agree.
    """

    receipt_path = references / "literature_confirmation_receipt.json"
    if not receipt_path.is_file():
        return None, "confirmation_receipt_missing"
    receipt = _read_json(receipt_path, {})
    packet_path = references / "literature_confirmation_packet.json"
    packet = _read_json(packet_path, {})
    if not isinstance(receipt, Mapping) or not isinstance(packet, Mapping):
        return None, "confirmation_receipt_invalid"
    stored_binding = receipt.get("confirmation_binding")
    if (
        str(receipt.get("schema_version") or "") != "dpl.literature_confirmation_receipt.v1"
        or str(receipt.get("status") or "").casefold() != "confirmed"
        or not isinstance(stored_binding, Mapping)
        or packet.get("confirmation_binding") != stored_binding
    ):
        return None, "confirmation_receipt_stale_or_invalid"
    packet_hash = literature_confirmation_packet_hash(packet)
    if (
        str(packet.get("packet_hash") or "") != packet_hash
        or str(receipt.get("confirmation_packet_hash") or "") != packet_hash
    ):
        return None, "confirmation_receipt_stale_or_invalid"
    if stored_binding == dict(binding):
        return _sha256_path(receipt_path), "explicit_confirmation_receipt"
    if _is_equivalent_confirmation_after_derived_rebuild(
        packet,
        stored_binding,
        binding,
        references,
    ):
        return _sha256_path(receipt_path), "semantic_continuity_after_derived_rebuild"
    return None, "confirmation_receipt_stale_or_invalid"


def _literature_snapshot_hash(references: Path) -> str:
    snapshot = _read_json(references / "literature_snapshot.json", {})
    return str(snapshot.get("snapshot_hash") or "").strip() if isinstance(snapshot, Mapping) else ""


def build_literature_teaching_corpus(project: str | Path) -> dict[str, Any]:
    """Build the only literature set that may be projected into learner HTML.

    A work is admitted only when all three Core contracts agree:

    * the canonical reference registry contains the work;
    * the active literature snapshot contains a matching citation key; and
    * the reference usage plan binds it to the current project.

    This intentionally rejects a broadly matching document, even a complete
    PDF, when it lacks a project role binding.
    """

    root = Path(project).expanduser().resolve()
    references = root / "references"
    registry_path = references / "reference_registry.json"
    usage_path = references / "reference_usage_plan.json"
    active_path = _active_literature_path(references)
    registry = _read_json(registry_path, {})
    usage = _read_json(usage_path, {})
    active = _read_json(active_path, {}) if active_path is not None else {}
    records = _items(registry, "records")
    usage_entries = _items(usage, "entries")
    active_items = _items(active, "items", "records")

    registry_by_key = {
        str(record.get("citation_key") or "").strip(): record
        for record in records
        if str(record.get("citation_key") or "").strip() and str(record.get("canonical_work_id") or "").strip()
    }
    active_by_key = {
        str(item.get("bibtex_key") or item.get("citation_key") or "").strip(): item
        for item in active_items
        if str(item.get("bibtex_key") or item.get("citation_key") or "").strip()
    }
    usage_by_key = {
        str(item.get("citation_key") or item.get("bibtex_key") or "").strip(): item
        for item in usage_entries
        if str(item.get("citation_key") or item.get("bibtex_key") or "").strip()
    }

    shared_keys = sorted(set(registry_by_key) & set(active_by_key) & set(usage_by_key))
    source_artifacts = [
        artifact
        for artifact in (
            _artifact_ref(root, registry_path, "canonical_reference_registry"),
            _artifact_ref(root, usage_path, "reference_usage_plan"),
            _artifact_ref(root, active_path, "active_literature_snapshot") if active_path is not None else None,
        )
        if artifact is not None
    ]
    confirmation_binding = literature_confirmation_binding(root)
    receipt_hash, confirmation_source = _confirmation_receipt(references, confirmation_binding)
    snapshot_hash = _literature_snapshot_hash(references)
    accepted_works: list[dict[str, Any]] = []
    for index, key in enumerate(shared_keys, start=1):
        record = registry_by_key[key]
        item = active_by_key[key]
        usage_entry = usage_by_key[key]
        active_index = active_items.index(item)
        usage_index = usage_entries.index(usage_entry)
        registry_index = records.index(record)
        title = str(record.get("title_original") or item.get("title") or usage_entry.get("title") or key).strip()
        identifiers = {
            name: str(value).strip()
            for name, value in {
                "doi": record.get("doi_normalized") or item.get("doi"),
                "arxiv": record.get("arxiv_id") or item.get("arxiv_id"),
                "url": record.get("canonical_url") or item.get("url"),
            }.items()
            if str(value or "").strip()
        }
        selector = f"/items/{active_index}" if item in active_items else "/"
        accepted_works.append(
            {
                "canonical_work_id": str(record["canonical_work_id"]),
                "citation_key": key,
                "title": title,
                "year": str(record.get("year") or item.get("year") or ""),
                "identifiers": identifiers,
                "selection_state": "accepted",
                # This is a deterministic presentation link, not an input to
                # paper identity.  The index renderer projects the same
                # confirmed order and stamps the same corpus hash into every
                # HTML page.
                "summary_detail_path": _summary_detail_path(index, key),
                "citation_eligibility": str(item.get("citation_eligibility") or "eligible"),
                "current_project_use": str(
                    usage_entry.get("citation_intent") or usage_entry.get("evidence_summary") or "project_role_bound"
                ),
                "role_bindings": [
                    {
                        "citation_role": str(usage_entry.get("citation_role") or ""),
                        "target_section": str(usage_entry.get("target_section") or ""),
                        "citation_intent": str(usage_entry.get("citation_intent") or ""),
                        "claim_scope": usage_entry.get("claim_scope") or [],
                    }
                ],
                "research_question_ids": list(usage_entry.get("research_question_ids") or []),
                "claim_ids": list(usage_entry.get("claim_ids") or []),
                "data_role_ids": list(usage_entry.get("data_role_ids") or []),
                "method_ids": list(usage_entry.get("method_ids") or []),
                "usage_plan_entry": {
                    key: usage_entry.get(key)
                    for key in (
                        "citation_key",
                        "required",
                        "target_section",
                        "citation_role",
                        "citation_intent",
                        "claim_scope",
                        "evidence_summary",
                    )
                },
                "source_artifacts": [
                    {
                        "relative_path": active_path.relative_to(root).as_posix() if active_path is not None else "",
                        "sha256": _semantic_sha256_path(active_path) if active_path is not None else "",
                        "selector": selector,
                        "kind": "active_literature_item",
                    },
                    {
                        "relative_path": usage_path.relative_to(root).as_posix(),
                        "sha256": _semantic_sha256_path(usage_path) or "",
                        "selector": f"/entries/{usage_index}",
                        "kind": "reference_usage_plan_entry",
                    },
                    {
                        "relative_path": registry_path.relative_to(root).as_posix(),
                        "sha256": _semantic_sha256_path(registry_path) or "",
                        "selector": f"/records/{registry_index}",
                        "kind": "canonical_reference_registry_record",
                    },
                ],
                "required_teaching_depth": _required_teaching_depth(usage_entry),
                "discipline_tags": list(item.get("discipline_tags") or []),
                "abstract": str(item.get("abstract") or "").strip(),
            }
        )

    rejected_keys = sorted((set(active_by_key) | set(usage_by_key)) - set(shared_keys))
    excluded_works = [
        {
            "citation_key": key,
            "selection_state": "excluded",
            "reason": _exclusion_reason(key, registry_by_key, active_by_key, usage_by_key),
        }
        for key in rejected_keys
    ]
    canonical = {
        "project_id": str(registry.get("project_id") or ""),
        "registry_hash": _semantic_sha256_path(registry_path),
        "usage_plan_hash": _semantic_sha256_path(usage_path),
        "active_snapshot_hash": _semantic_sha256_path(active_path) if active_path is not None else None,
        "snapshot_hash": snapshot_hash,
        "confirmation_receipt_hash": receipt_hash,
        "confirmation_source": confirmation_source,
        "confirmation_binding": confirmation_binding,
        "accepted_works": [_corpus_identity_work(item) for item in accepted_works],
        "excluded_works": excluded_works,
        "source_artifacts": source_artifacts,
    }
    corpus_hash = _canonical_hash(canonical)
    registry_ready = str(registry.get("status") or "").casefold() == "ready"
    registry_keys = set(registry_by_key)
    active_keys = set(active_by_key)
    usage_keys = set(usage_by_key)
    expected_keys = registry_keys
    active_subset_contract = bool(shared_keys) and active_keys <= registry_keys and active_keys <= usage_keys
    legacy_full_contract = set(shared_keys) == expected_keys
    contracts_agree = registry_ready and (active_subset_contract or legacy_full_contract)
    status = "confirmed" if contracts_agree and receipt_hash is not None else "confirmation_pending" if contracts_agree else "incomplete"
    return {
        "schema_version": TEACHING_CORPUS_SCHEMA,
        "project_id": canonical["project_id"],
        "snapshot_hash": snapshot_hash,
        "corpus_status": status,
        "corpus_snapshot_hash": corpus_hash,
        "research_plan_hash": _research_plan_hash(root),
        "confirmation_receipt_hash": receipt_hash,
        "confirmation_source": confirmation_source,
        "confirmation_binding": confirmation_binding,
        "accepted_works": accepted_works,
        "excluded_works": excluded_works,
        "source_artifacts": source_artifacts,
        "set_integrity": {
            "registry_work_count": len(registry_by_key),
            "active_work_count": len(active_by_key),
            "usage_plan_work_count": len(usage_by_key),
            "accepted_work_count": len(accepted_works),
            "missing_from_active": sorted(expected_keys - set(active_by_key)),
            "missing_from_usage_plan": sorted(expected_keys - set(usage_by_key)),
            "extra_active_or_usage_work_count": len(excluded_works),
        },
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _research_plan_hash(root: Path) -> str | None:
    for name in ("research_plan/research_plan.md", "research_plan/research_plan.zh-CN.md"):
        path = root / name
        digest = _sha256_path(path)
        if digest:
            return digest
    return None


def _required_teaching_depth(usage_entry: Mapping[str, Any]) -> str:
    role = str(usage_entry.get("citation_role") or "").casefold()
    if role in {"dataset_provenance", "method_or_tool_background", "mechanism_or_interpretation"}:
        return "analysis_ready"
    return "abstract_ready"


def _exclusion_reason(
    key: str,
    registry: Mapping[str, Any],
    active: Mapping[str, Any],
    usage: Mapping[str, Any],
) -> str:
    missing = []
    if key not in registry:
        missing.append("not_in_canonical_registry")
    if key not in active:
        missing.append("not_in_active_literature_snapshot")
    if key not in usage:
        missing.append("no_project_role_binding")
    return ";".join(missing) or "not_admitted"


def write_literature_teaching_corpus(project: str | Path) -> dict[str, Any]:
    """Materialize the manifest atomically under the project ``references`` root."""

    root = Path(project).expanduser().resolve()
    document = build_literature_teaching_corpus(root)
    target = root / TEACHING_CORPUS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = _read_json(target, {})
    if (
        isinstance(previous, Mapping)
        and previous.get("corpus_snapshot_hash") == document.get("corpus_snapshot_hash")
        and previous.get("generated_at")
    ):
        document["generated_at"] = previous["generated_at"]
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return document


__all__ = [
    "TEACHING_CORPUS_PATH",
    "TEACHING_CORPUS_SCHEMA",
    "build_literature_teaching_corpus",
    "literature_confirmation_binding",
    "literature_confirmation_packet_hash",
    "write_literature_teaching_corpus",
]
