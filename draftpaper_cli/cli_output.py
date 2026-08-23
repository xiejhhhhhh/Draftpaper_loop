"""Compact human-facing CLI output while retaining full JSON artifacts on disk."""

from __future__ import annotations

from typing import Any


_HUMAN_REVIEW_PATH_KEYS = (
    "primary_human_review_html",
    "human_decision_html",
    "stage_summary_zh_html",
    "decision_html",
)


def _artifact_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, value in payload.items():
        lowered = str(key).lower()
        if isinstance(value, str) and ("path" in lowered or lowered.endswith(("report", "manifest", "packet"))):
            if "/" in value or "\\" in value or value.endswith((".json", ".html", ".md", ".pdf", ".tex", ".yaml")):
                paths.append(value)
    return list(dict.fromkeys(paths))[:8]


def _human_review_reference(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """Return the usable author-facing HTML reference, without inferring paths."""

    for key in _HUMAN_REVIEW_PATH_KEYS:
        value = payload.get(key)
        if isinstance(value, dict) and (
            isinstance(value.get("project_relative_path"), str) or isinstance(value.get("absolute_path"), str)
        ):
            return key, value
    return None, None


def prioritize_human_review(payload: Any) -> Any:
    """Put the readable confirmation page first and keep the audit attachment last.

    The normal terminal is often non-interactive when called by an Agent, so
    compact output alone cannot enforce the author-review ordering.  This
    function preserves every field in a full JSON result while making the
    author-facing page the first actionable artifact.
    """

    if not isinstance(payload, dict):
        return payload
    review_key, human_review = _human_review_reference(payload)
    if review_key is None or human_review is None:
        return payload
    ordered: dict[str, Any] = {review_key: human_review}
    for key in (
        "stage_completion_summary_zh",
        "decision_question_zh",
        "decision_summary_zh",
        "semantic_delta_summary_zh",
        "semantic_delta_summary_en",
        "review_points_zh",
        "decision_actor_type",
        "decision_authority_reason_zh",
        "confirmation_meaning_zh",
        "confirmation_command",
    ):
        value = payload.get(key)
        if key != review_key and value not in (None, [], {}):
            ordered[key] = value
    excluded = set(ordered) | {"technical_audit_html", "technical_audit_json"}
    ordered.update({key: value for key, value in payload.items() if key not in excluded})
    technical_audit_key = "technical_audit_json" if payload.get("technical_audit_json") not in (None, [], {}) else "technical_audit_html"
    technical_audit = payload.get(technical_audit_key)
    if technical_audit not in (None, [], {}):
        ordered[technical_audit_key] = technical_audit
    return ordered


def compact_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    payload = prioritize_human_review(payload)
    _review_key, human_review = _human_review_reference(payload)
    if isinstance(human_review, dict):
        # Checkpoint output is an author interaction, not a generic command
        # diagnostic. Keep the mandatory review material first even in TTY
        # compact mode, then expose optional technical and workflow details.
        ordered = {
            "primary_human_review_html": human_review,
            "stage_completion_summary_zh": payload.get("stage_completion_summary_zh") or payload.get("stage_narrative_zh"),
            "semantic_delta_summary_zh": payload.get("semantic_delta_summary_zh"),
            "semantic_delta_summary_en": payload.get("semantic_delta_summary_en"),
            "review_points_zh": payload.get("review_points_zh"),
            "decision_actor_type": payload.get("decision_actor_type"),
            "decision_authority_reason_zh": payload.get("decision_authority_reason_zh"),
            "confirmation_meaning_zh": payload.get("confirmation_meaning_zh"),
            "confirmation_command": payload.get("confirmation_command"),
            "status": payload.get("status") or payload.get("decision") or "completed",
            "checkpoint_hash": payload.get("checkpoint_hash"),
            "scientific_decision_sha256": payload.get("scientific_decision_sha256"),
            "continuity_status": (payload.get("confirmation_continuity") or {}).get("classification") if isinstance(payload.get("confirmation_continuity"), dict) else payload.get("continuity_status"),
            "unresolved_issues": payload.get("unresolved_issues"),
            "verified_next_action": payload.get("verified_next_action") or payload.get("next_action") or payload.get("recommended_next_action"),
            "technical_audit_json": payload.get("technical_audit_json"),
            "technical_audit_html": payload.get("technical_audit_html"),
        }
        return {key: value for key, value in ordered.items() if value not in (None, [], {})}
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    failures = payload.get("failure_routes") if isinstance(payload.get("failure_routes"), list) else []
    snapshot = payload.get("snapshot_id") or payload.get("evidence_snapshot_id")
    if not snapshot and isinstance(payload.get("evidence_snapshot"), dict):
        snapshot = payload["evidence_snapshot"].get("snapshot_id")
    next_action = payload.get("verified_next_action") or payload.get("next_action") or payload.get("recommended_next_action")
    result: dict[str, Any] = {
        "status": payload.get("status") or payload.get("decision") or "completed",
        "decision": payload.get("decision"),
        "current_snapshot": snapshot,
        "blocking_issue_count": payload.get("error_count") if payload.get("error_count") is not None else len(failures),
        "top_issues": [
            {
                "code": item.get("code") or item.get("predicate"),
                "message": item.get("message") or item.get("reason"),
                "artifact": item.get("path") or item.get("artifact"),
            }
            for item in [*issues, *failures][:5]
            if isinstance(item, dict)
        ],
        "artifact_paths": _artifact_paths(payload),
        "verified_next_action": next_action,
    }
    return {key: value for key, value in result.items() if value not in (None, [], {})}
