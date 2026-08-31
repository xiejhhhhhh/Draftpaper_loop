"""Materialize a hash-bound active literature snapshot from explicit decisions.

The search stage deliberately keeps a broad operational candidate pool.  This
module is the missing bridge between that pool and the ``active_literature``
contract consumed by the confirmed teaching corpus.  It never guesses a final
corpus from directory contents: an admission manifest must cover every
candidate and state an explicit accept, exclude, or defer decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project

ADMISSION_PACKET_PATH = "references/literature_admission_packet.json"
ADMISSION_PACKET_MARKDOWN = "references/literature_admission_packet.zh-CN.md"
ADMISSION_RECEIPT_PATH = "references/literature_admission_receipt.json"
ACTIVE_LITERATURE_PATH = "references/active_literature.json"

ADMISSION_PACKET_SCHEMA = "dpl.literature_admission_packet.v1"
ADMISSION_DECISION_SCHEMA = "dpl.literature_admission_decisions.v1"
ADMISSION_RECEIPT_SCHEMA = "dpl.literature_admission_receipt.v1"
ACTIVE_LITERATURE_SCHEMA = "dpl.active_literature.v1"

_VOLATILE_KEYS = frozenset(
    {
        "created_at",
        "generated_at",
        "updated_at",
        "written_at",
        "activated_at",
        "packet_hash",
        "decision_hash",
        "receipt_hash",
    }
)
_DECISIONS = frozenset({"accept", "exclude", "defer"})
_REJECTED_STATES = frozenset({"rejected", "quarantined", "excluded"})


class LiteratureAdmissionError(RuntimeError):
    """Raised when an admission packet or decision manifest is invalid."""


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(item) for key, item in value.items() if str(key) not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _hash_value(value: Mapping[str, Any]) -> str:
    material = json.dumps(_stable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    try:
        payload = _read_json(path, None)
        if isinstance(payload, Mapping):
            return _hash_value(payload)
        if isinstance(payload, list):
            return _hash_value({"items": payload})
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _items(document: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(document, Mapping):
        for key in keys:
            value = document.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(document, list):
        return [dict(item) for item in document if isinstance(item, Mapping)]
    return []


def _citation_key(item: Mapping[str, Any]) -> str:
    return str(item.get("bibtex_key") or item.get("citation_key") or "").strip()


def _canonical_work_id(item: Mapping[str, Any]) -> str:
    return str(item.get("canonical_work_id") or item.get("work_id") or "").strip()


def _source_binding(references: Path) -> dict[str, Any]:
    names = (
        "literature_items.json",
        "reference_registry.json",
        "reference_usage_plan.json",
        "literature_snapshot.json",
        "literature_relevance_report.json",
        "paper_fetch_manifest.json",
    )
    return {name: _file_hash(references / name) for name in names if (references / name).is_file()}


def _candidate_recommendation(item: Mapping[str, Any]) -> tuple[str, list[str]]:
    state = str(item.get("candidate_state") or "").casefold()
    gate = str(item.get("gate_state") or "").casefold()
    eligibility = str(item.get("citation_eligibility") or "").casefold()
    reasons: list[str] = []
    if gate in _REJECTED_STATES or state in _REJECTED_STATES:
        reasons.append("当前相关性或隔离门禁已拒绝，不能静默进入正式语料")
        return "exclude", reasons
    if bool(item.get("retained")) and eligibility not in {
        "not_eligible",
        "not_eligible_pending_review",
    }:
        reasons.append("已有明确保留标记且引用资格已通过")
        return "accept", reasons
    if state == "relevance_passed":
        reasons.append("主题门禁通过，但仍需为当前项目确认具体角色和证据边界")
        return "review_required", reasons
    if state == "review_required":
        reasons.append("候选仍处于待审状态，需要显式决定是否纳入")
        return "review_required", reasons
    reasons.append("候选状态不足以自动判断正式准入")
    return "review_required", reasons


def _role_summary(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    return {
        key: entry.get(key)
        for key in (
            "citation_role",
            "target_section",
            "citation_intent",
            "claim_scope",
            "research_question_ids",
            "claim_ids",
            "data_role_ids",
            "method_ids",
        )
        if key in entry
    }


def _packet_hash(packet: Mapping[str, Any]) -> str:
    return _hash_value({str(key): value for key, value in packet.items() if str(key) != "packet_hash"})


def _decision_hash(decisions: Mapping[str, Any]) -> str:
    return _hash_value({str(key): value for key, value in decisions.items() if str(key) != "decision_hash"})


def _load_candidate_pool(references: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    items = _items(_read_json(references / "literature_items.json", []), "items")
    registry = _items(_read_json(references / "reference_registry.json", {}), "records")
    usage = _items(_read_json(references / "reference_usage_plan.json", {}), "entries")
    registry_by_key = {_citation_key(item): item for item in registry if _citation_key(item)}
    usage_by_key = {_citation_key(item): item for item in usage if _citation_key(item)}
    return items, registry_by_key, usage_by_key


def build_literature_admission_packet(project: str | Path) -> dict[str, Any]:
    """Write a candidate admission packet without activating any item."""

    state = load_project(project)
    references = state.path / "references"
    items, registry_by_key, usage_by_key = _load_candidate_pool(references)
    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(items, start=1):
        key = _citation_key(item)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        recommendation, reasons = _candidate_recommendation(item)
        registry = registry_by_key.get(key, {})
        usage = usage_by_key.get(key)
        candidates.append(
            {
                "candidate_id": f"ref-{index:04d}",
                "citation_key": key,
                "canonical_work_id": _canonical_work_id(registry) or _canonical_work_id(item),
                "title": str(item.get("title") or registry.get("title_original") or key).strip(),
                "year": str(item.get("year") or registry.get("year") or ""),
                "candidate_state": str(item.get("candidate_state") or "unknown"),
                "gate_state": str(item.get("gate_state") or ""),
                "citation_eligibility": str(item.get("citation_eligibility") or ""),
                "reference_origin": str(item.get("reference_origin") or "external_search"),
                "role_summary": _role_summary(usage),
                "supported_roles": sorted(
                    str(role)
                    for role, evidence in (item.get("role_evidence") or {}).items()
                    if isinstance(evidence, Mapping) and evidence.get("supported")
                ),
                "fulltext_status": str(item.get("pdf_read_status") or "not_bound"),
                "recommended_decision": recommendation,
                "recommendation_reasons": reasons,
            }
        )
    packet: dict[str, Any] = {
        "schema_version": ADMISSION_PACKET_SCHEMA,
        "status": "ready_for_admission_decision",
        "project_id": str(state.metadata.get("project_id") or ""),
        "project_path": "<project>",
        "source_binding": _source_binding(references),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "policy": {
            "requires_explicit_decision_for_every_candidate": True,
            "search_candidates_are_not_teaching_evidence": True,
            "excluded_or_deferred_items_are_not_written_to_active_snapshot": True,
            "gate_override_requires_reason": True,
            "confirmation_is_separate": True,
        },
    }
    packet["packet_hash"] = _packet_hash(packet)
    _write_json(references / Path(ADMISSION_PACKET_PATH).name, packet)
    lines = [
        "# 文献正式准入包",
        "",
        "> 这一步只把候选池整理为可审计的准入决定输入，不会把任何候选自动变成正式教学语料。",
        "",
        f"- 候选数量：**{len(candidates)}**",
        f"- 准入包哈希：`{packet['packet_hash']}`",
        "- 决定要求：每篇候选都必须明确 `accept`、`exclude` 或 `defer`。",
        "",
        "## 候选清单",
        "",
        "| 序号 | citation key | 推荐状态 | 当前状态 | 标题 |",
        "|---:|---|---|---|---|",
    ]
    for index, candidate in enumerate(candidates, start=1):
        title = str(candidate["title"]).replace("|", "\\|")
        lines.append(
            f"| {index} | `{candidate['citation_key']}` | `{candidate['recommended_decision']}` | "
            f"`{candidate['candidate_state'] or 'unknown'}` | {title} |"
        )
    lines.extend(
        [
            "",
            "## 决定边界",
            "",
            "- `accept` 才会进入 active_literature；`exclude` 和 `defer` 只保留在准入收据中。",
            "- 对门禁拒绝或待审条目进行 `accept` 时，决定清单必须给出具体的项目角色和覆盖理由。",
            "- active_literature 生成后，仍需通过 `review-literature-coverage` 和 `confirm-literature-corpus` 才能发布教学语料。",
            "",
        ]
    )
    (references / Path(ADMISSION_PACKET_MARKDOWN).name).write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": packet["status"],
        "project_path": str(state.path),
        "packet": ADMISSION_PACKET_PATH,
        "markdown": ADMISSION_PACKET_MARKDOWN,
        "candidate_count": len(candidates),
        "packet_hash": packet["packet_hash"],
    }


def _validate_decisions(
    packet: Mapping[str, Any],
    decisions: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if str(decisions.get("schema_version") or "") != ADMISSION_DECISION_SCHEMA:
        raise LiteratureAdmissionError("The decision file has an unsupported schema_version.")
    if str(decisions.get("packet_hash") or "") != str(packet.get("packet_hash") or ""):
        raise LiteratureAdmissionError("The decision file is not bound to the current admission packet hash.")
    rows = decisions.get("decisions")
    if not isinstance(rows, list):
        raise LiteratureAdmissionError("The decision file must contain a decisions list.")
    candidate_rows = [row for row in packet.get("candidates") or () if isinstance(row, Mapping)]
    expected = {str(row.get("citation_key") or "") for row in candidate_rows}
    provided: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise LiteratureAdmissionError("Every admission decision must be an object.")
        key = str(row.get("citation_key") or "").strip()
        if not key or key in provided:
            raise LiteratureAdmissionError(f"Admission decisions contain a missing or duplicate citation key: {key!r}.")
        decision = str(row.get("decision") or "").casefold().strip()
        if decision not in _DECISIONS:
            raise LiteratureAdmissionError(f"Unsupported admission decision for {key}: {decision!r}.")
        reason = str(row.get("reason") or "").strip()
        if len(reason) < 12:
            raise LiteratureAdmissionError(f"Admission decision for {key} needs a concrete reason.")
        provided[key] = dict(row)
    missing = sorted(expected - set(provided))
    unknown = sorted(set(provided) - expected)
    if missing:
        raise LiteratureAdmissionError("Admission decisions are missing: " + ", ".join(missing))
    if unknown:
        raise LiteratureAdmissionError("Admission decisions contain unknown candidates: " + ", ".join(unknown))
    return candidate_rows, provided


def activate_literature_corpus(
    project: str | Path,
    *,
    packet_hash: str,
    decision_file: str,
) -> dict[str, Any]:
    """Apply a complete decision manifest and write the active snapshot."""

    state = load_project(project)
    references = state.path / "references"
    packet_path = references / Path(ADMISSION_PACKET_PATH).name
    packet = _read_json(packet_path, {})
    if not isinstance(packet, Mapping) or str(packet.get("schema_version") or "") != ADMISSION_PACKET_SCHEMA:
        raise LiteratureAdmissionError("Run prepare-literature-admission before activating the corpus.")
    expected_packet_hash = _packet_hash(packet)
    if str(packet.get("packet_hash") or "") != expected_packet_hash or packet_hash != expected_packet_hash:
        raise LiteratureAdmissionError("The supplied admission packet hash does not match the current packet.")
    decisions_path = Path(decision_file).expanduser().resolve()
    decisions = _read_json(decisions_path, {})
    if not isinstance(decisions, Mapping):
        raise LiteratureAdmissionError("The admission decision file is not valid JSON.")
    candidate_rows, by_key = _validate_decisions(packet, decisions)
    items, registry_by_key, usage_by_key = _load_candidate_pool(references)
    items_by_key = {_citation_key(item): item for item in items if _citation_key(item)}
    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        key = str(candidate.get("citation_key") or "")
        row = by_key[key]
        decision = str(row.get("decision") or "").casefold().strip()
        item = items_by_key.get(key)
        if item is None:
            raise LiteratureAdmissionError(f"Candidate {key} disappeared from literature_items.json after packet creation.")
        registry = registry_by_key.get(key, {})
        usage = usage_by_key.get(key)
        canonical_id = _canonical_work_id(registry) or _canonical_work_id(item)
        if decision == "accept":
            if not canonical_id:
                raise LiteratureAdmissionError(f"Accepted candidate {key} has no canonical work identity.")
            if usage is None:
                raise LiteratureAdmissionError(f"Accepted candidate {key} has no project role binding.")
            gate_rejected = (
                str(candidate.get("gate_state") or "").casefold() in _REJECTED_STATES
                or str(candidate.get("candidate_state") or "").casefold() in _REJECTED_STATES
            )
            if gate_rejected and not bool(row.get("gate_override")):
                raise LiteratureAdmissionError(
                    f"Accepted candidate {key} is gate-rejected; set gate_override=true and explain the evidence-based override."
                )
            enriched = dict(item)
            enriched["admission_state"] = "accepted"
            enriched["admission_reason"] = str(row["reason"]).strip()
            enriched["admission_roles"] = row.get("roles") or _role_summary(usage)
            enriched["admission_gate_override"] = bool(row.get("gate_override"))
            enriched["admission_canonical_work_id"] = canonical_id
            accepted.append(enriched)
        elif decision == "defer":
            deferred.append({"citation_key": key, "title": candidate.get("title"), "reason": row["reason"]})
        else:
            excluded.append({"citation_key": key, "title": candidate.get("title"), "reason": row["reason"]})
    if not accepted:
        raise LiteratureAdmissionError("The admission decision manifest accepted no canonical work.")
    decision_document = dict(decisions)
    expected_decision_hash = _decision_hash(decision_document)
    declared_decision_hash = str(decisions.get("decision_hash") or "")
    if declared_decision_hash and declared_decision_hash != expected_decision_hash:
        raise LiteratureAdmissionError("The admission decision file has an invalid decision_hash.")
    decision_hash = declared_decision_hash or expected_decision_hash
    previous = _read_json(references / Path(ACTIVE_LITERATURE_PATH).name, {})
    generated_at = str(previous.get("generated_at") or "") if isinstance(previous, Mapping) else ""
    active: dict[str, Any] = {
        "schema_version": ACTIVE_LITERATURE_SCHEMA,
        "status": "active",
        "project_id": str(state.metadata.get("project_id") or ""),
        "generated_at": generated_at or utc_now(),
        "source_binding": packet.get("source_binding") or {},
        "admission_packet_hash": expected_packet_hash,
        "decision_hash": decision_hash,
        "decision_mode": str(decisions.get("decision_mode") or "explicit_manifest"),
        "decided_by": str(decisions.get("decided_by") or "unspecified"),
        "items": accepted,
        "admission_summary": {
            "candidate_count": len(candidate_rows),
            "accepted_count": len(accepted),
            "excluded_count": len(excluded),
            "deferred_count": len(deferred),
            "excluded": excluded,
            "deferred": deferred,
        },
        "policy": {
            "not_a_teaching_confirmation": True,
            "requires_confirm_literature_corpus": True,
            "rejected_and_deferred_candidates_remain_outside_active_snapshot": True,
        },
    }
    _write_json(references / Path(ACTIVE_LITERATURE_PATH).name, active)
    receipt = {
        "schema_version": ADMISSION_RECEIPT_SCHEMA,
        "status": "activated",
        "activated_at": utc_now(),
        "project_id": str(state.metadata.get("project_id") or ""),
        "admission_packet": ADMISSION_PACKET_PATH,
        "admission_packet_hash": expected_packet_hash,
        "decision_file": str(decisions_path),
        "decision_hash": decision_hash,
        "decision_mode": str(decisions.get("decision_mode") or "explicit_manifest"),
        "decided_by": str(decisions.get("decided_by") or "unspecified"),
        "accepted_citation_keys": [_citation_key(item) for item in accepted],
        "excluded_citation_keys": [str(item["citation_key"]) for item in excluded],
        "deferred_citation_keys": [str(item["citation_key"]) for item in deferred],
        "source_binding": packet.get("source_binding") or {},
        "active_literature": ACTIVE_LITERATURE_PATH,
    }
    receipt["receipt_hash"] = _hash_value(receipt)
    _write_json(references / Path(ADMISSION_RECEIPT_PATH).name, receipt)
    return {
        "status": "activated",
        "project_path": str(state.path),
        "active_literature": ACTIVE_LITERATURE_PATH,
        "receipt": ADMISSION_RECEIPT_PATH,
        "admission_packet_hash": expected_packet_hash,
        "decision_hash": decision_hash,
        "accepted_work_count": len(accepted),
        "excluded_work_count": len(excluded),
        "deferred_work_count": len(deferred),
        "next_command": f'python -m draftpaper_cli.cli review-literature-coverage --project "{state.path}"',
    }


__all__ = [
    "ACTIVE_LITERATURE_PATH",
    "ADMISSION_PACKET_PATH",
    "ADMISSION_RECEIPT_PATH",
    "LiteratureAdmissionError",
    "activate_literature_corpus",
    "build_literature_admission_packet",
]
