"""Post-fetch discipline, topic, role, and citation-eligibility assessment."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .literature_relevance import score_reference
from .paper_identity_resolution import revalidate_identity_after_fetch
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


POSTFETCH_SCHEMA = "dpl.postfetch_relevance_assessment.v1"
POSTFETCH_REPORT = "references/postfetch_relevance_report.json"
QUARANTINED_CANDIDATES = "references/quarantined_literature_candidates.json"


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _has_evidence(item: dict[str, Any]) -> bool:
    return bool(
        str(item.get("abstract") or "").strip()
        or str(item.get("pdf_text_excerpt") or "").strip()
        or item.get("evidence_passages")
        or item.get("document_parses")
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _quarantine_generated_fetches(project: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    fulltext_root = (project / "references" / "fulltext").resolve()
    for item in items:
        relative = str(item.get("paper_fetch_markdown_path") or "")
        if not relative:
            continue
        source = Path(relative)
        if not source.is_absolute():
            source = project / source
        if not source.is_file():
            continue
        resolved_source = source.resolve()
        if fulltext_root not in resolved_source.parents:
            continue
        digest = _file_sha256(resolved_source)
        target = project / "references" / "quarantine" / "rejected_candidates" / digest.removeprefix("sha256:")[:32] / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            if _file_sha256(target) != digest:
                raise ValueError(f"Quarantine target hash conflict: {target}")
            resolved_source.unlink()
        else:
            shutil.move(str(resolved_source), str(target))
        record = {
            "candidate_id": str((item.get("identity_resolution_receipt") or {}).get("candidate_id") or ""),
            "work_id": str(item.get("resolved_work_id") or item.get("work_id") or ""),
            "from": resolved_source.relative_to(project.resolve()).as_posix(),
            "to": target.relative_to(project).as_posix(),
            "sha256": digest,
            "reason": item.get("postfetch_state"),
            "rollback_route": "review and re-fetch after identity/relevance correction",
        }
        item["quarantine_artifact"] = record
        item["paper_fetch_markdown_path"] = record["to"]
        records.append(record)
    return records


def assess_postfetch_candidate(item: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    value = revalidate_identity_after_fetch(item)
    scoring_value = dict(value)
    resolved_metadata = value.get("paper_fetch_resolved_metadata")
    if isinstance(resolved_metadata, dict):
        for field in ("title", "authors", "year", "doi", "publication"):
            if resolved_metadata.get(field):
                scoring_value[field] = resolved_metadata[field]
    scores = score_reference(scoring_value, contract)
    value.update(scores)
    identity_status = str(value.get("identity_resolution_status") or "unresolved")
    prefetch_state = str(value.get("gate_state") or value.get("candidate_state") or "review_required")
    discipline_state = str(scores["discipline_assessment"].get("state") or "review_required")
    topic_score = float(scores.get("topic_relevance_score") or 0.0)
    fetch_decision = value.get("fulltext_fetch_decision") if isinstance(value.get("fulltext_fetch_decision"), dict) else {}
    fetch_required = bool(fetch_decision.get("fetch"))
    reasons: list[str] = []

    if identity_status == "mismatch":
        state = "rejected_identity_mismatch"
        reasons.append("identity_mismatch")
    elif identity_status in {"ambiguous", "unresolved", "provider_degraded", "no_access", "rate_limited"}:
        state = "review_required"
        reasons.append(f"identity_{identity_status}")
    elif discipline_state == "rejected":
        state = "rejected_discipline_mismatch"
        reasons.extend(str(value) for value in scores["discipline_assessment"].get("reason_codes") or [])
    elif topic_score < 0.35 or scores["topic_evidence"].get("generic_only_match"):
        state = "rejected_topic_mismatch"
        reasons.append("topic_mismatch_after_fetch")
    elif fetch_required and not _has_evidence(value):
        execution_status = str(value.get("paper_fetch_execution_status") or "failed")
        if execution_status in {"unavailable", "degraded", "provider_degraded", "rate_limited", "no_access"}:
            state = "review_required"
            reasons.append(f"fulltext_provider_{execution_status}")
        else:
            state = "rejected_insufficient_evidence"
            reasons.append("required_fulltext_evidence_unavailable")
    elif prefetch_state in {"curated_unverified", "review_required"}:
        role = str(scores["discipline_assessment"].get("cross_discipline_role") or "")
        if role and topic_score >= 0.55 and _has_evidence(value):
            state = "accepted_context_only"
            reasons.append("explicit_cross_discipline_context")
        elif prefetch_state == "curated_unverified" and identity_status in {"resolved_exact", "resolved_probable"}:
            state = "accepted_context_only"
            reasons.append("user_curated_context_only_until_citation_review")
        else:
            state = "review_required"
            reasons.append("prefetch_review_not_resolved")
    elif topic_score < 0.55 or discipline_state == "review_required":
        state = "review_required"
        reasons.append("postfetch_borderline")
    else:
        state = "accepted_active"
        reasons.append("postfetch_topic_discipline_identity_passed")

    eligibility = {
        "accepted_active": "eligible_for_declared_role",
        "accepted_context_only": "context_only",
        "review_required": "not_eligible_pending_review",
    }.get(state, "not_eligible")
    assessment = {
        "schema_version": POSTFETCH_SCHEMA,
        "candidate_id": str((value.get("identity_resolution_receipt") or {}).get("candidate_id") or ""),
        "work_id": str(value.get("resolved_work_id") or value.get("work_id") or ""),
        "status": state,
        "reason_codes": list(dict.fromkeys(reasons)),
        "identity_status": identity_status,
        "prefetch_state": prefetch_state,
        "topic_relevance_score": topic_score,
        "discipline_state": discipline_state,
        "citation_eligibility": eligibility,
        "input_hash": _canonical_hash(
            {
                "title": value.get("title"),
                "doi": value.get("doi"),
                "abstract": value.get("abstract"),
                "pdf_text_excerpt": value.get("pdf_text_excerpt"),
                "identity_status": identity_status,
                "fetch_decision_hash": fetch_decision.get("decision_hash"),
            }
        ),
        "generated_at": utc_now(),
    }
    value["postfetch_relevance"] = assessment
    value["postfetch_state"] = state
    value["citation_eligibility"] = eligibility
    value["candidate_state"] = state
    return value


def assess_postfetch_candidates(
    project: str | Path,
    items: list[dict[str, Any]],
    contract: dict[str, Any],
    *,
    prefetch_rejected: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    state = load_project(project)
    assessed = [assess_postfetch_candidate(item, contract) for item in items]
    active_states = {"accepted_active", "accepted_context_only"}
    active = [item for item in assessed if item.get("postfetch_state") in active_states]
    inactive = [item for item in assessed if item.get("postfetch_state") not in active_states]
    quarantine = [
        *[
            {
                **dict(item),
                "postfetch_state": "rejected_prefetch",
                "citation_eligibility": "not_eligible",
            }
            for item in (prefetch_rejected or [])
        ],
        *inactive,
    ]
    quarantine_artifacts = _quarantine_generated_fetches(state.path, quarantine)
    status_counts: dict[str, int] = {}
    for item in [*active, *quarantine]:
        status = str(item.get("postfetch_state") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    report = {
        "schema_version": "dpl.postfetch_relevance_report.v1",
        "status": "completed",
        "input_count": len(items) + len(prefetch_rejected or []),
        "assessed_count": len(assessed),
        "active_count": len(active),
        "quarantine_count": len(quarantine),
        "quarantine_artifact_count": len(quarantine_artifacts),
        "quarantine_artifacts": quarantine_artifacts,
        "status_counts": status_counts,
        "active_work_ids": [str(item.get("resolved_work_id") or item.get("work_id") or "") for item in active],
        "assessment_hash": _canonical_hash([item.get("postfetch_relevance") for item in assessed]),
        "query_contract_hash": _canonical_hash(contract),
        "generated_at": utc_now(),
        "assessments": [item.get("postfetch_relevance") for item in assessed],
    }
    _write_json(state.path / POSTFETCH_REPORT, report)
    _write_json(
        state.path / QUARANTINED_CANDIDATES,
        {
            "schema_version": "dpl.literature_quarantine_record.v1",
            "assessment_hash": report["assessment_hash"],
            "count": len(quarantine),
            "artifact_count": len(quarantine_artifacts),
            "artifacts": quarantine_artifacts,
            "items": quarantine,
        },
    )
    return active, quarantine, report
