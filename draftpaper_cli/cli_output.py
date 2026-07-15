"""Compact human-facing CLI output while retaining full JSON artifacts on disk."""

from __future__ import annotations

from typing import Any


def _artifact_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, value in payload.items():
        lowered = str(key).lower()
        if isinstance(value, str) and ("path" in lowered or lowered.endswith(("report", "manifest", "packet"))):
            if "/" in value or "\\" in value or value.endswith((".json", ".html", ".md", ".pdf", ".tex", ".yaml")):
                paths.append(value)
    return list(dict.fromkeys(paths))[:8]


def compact_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
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
