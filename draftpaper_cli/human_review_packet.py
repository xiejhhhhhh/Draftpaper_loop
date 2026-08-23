"""Versioned, user-facing review packets shared across decision families."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .state_kernel import atomic_write_json, atomic_write_text


HUMAN_REVIEW_PACKET_SCHEMA = "dpl.human_review_packet.v1"
RESEARCH_PLAN_PACKET_ROOT = "review/checkpoints"
RESEARCH_PLAN_ACTIVE_POINTER = "research_plan/active_review_packet.json"
RESEARCH_PLAN_COMPAT_JSON = "research_plan/research_plan_review_packet.json"
RESEARCH_PLAN_COMPAT_HTML = "research_plan/research_plan_review_packet.html"


class HumanReviewPacketError(RuntimeError):
    """Raised when a review packet would be unsafe or ambiguous."""


def _safe_packet_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value).strip("-")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _compat_html(target_relative: str) -> str:
    target = target_relative.replace("\\", "/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <title>Draftpaper-loop 研究计划审阅包</title>
</head>
<body>
  <p>当前研究计划审阅包：<a href="{target}">{target}</a></p>
</body>
</html>
"""


def _packet_dir(root: Path, packet_id: str) -> Path:
    output = (root / RESEARCH_PLAN_PACKET_ROOT / packet_id).resolve()
    try:
        output.relative_to(root.resolve())
    except ValueError as exc:
        raise HumanReviewPacketError("Research plan packet path escapes project root.") from exc
    return output


def active_research_plan_packet(root: str | Path) -> dict[str, Any] | None:
    project_root = Path(root)
    pointer = _load_json(project_root / RESEARCH_PLAN_ACTIVE_POINTER)
    relative = str(pointer.get("packet_path") or "")
    if not pointer or not relative:
        return None
    path = (project_root / relative).resolve()
    try:
        path.relative_to(project_root.resolve())
    except ValueError:
        return None
    packet = _load_json(path / "human_review_packet.json")
    if not packet:
        return None
    return {"pointer": pointer, "packet": packet, "packet_dir": path}


def mark_active_research_plan_packet_superseded(root: str | Path, *, reason: str) -> dict[str, Any] | None:
    project_root = Path(root)
    active = active_research_plan_packet(project_root)
    if not active:
        return None
    pointer = dict(active["pointer"])
    pointer["status"] = "superseded_pending_revision"
    pointer["superseded_reason"] = str(reason).strip()
    atomic_write_json(project_root / RESEARCH_PLAN_ACTIVE_POINTER, pointer)
    return pointer


def write_research_plan_review_packet(
    root: str | Path,
    *,
    brief: Mapping[str, Any],
    scientific_fingerprint: Mapping[str, Any],
    audit_fingerprint: Mapping[str, Any],
    presentation_fingerprint: Mapping[str, Any],
    semantic_delta: Mapping[str, Any],
    review_state: str,
    review_requirement: str,
    decision_status: str,
    unresolved_items: list[dict[str, Any]],
    revision_cycle_id: str | None,
    render_zh: str,
    render_en: str,
) -> dict[str, Any]:
    """Write a versioned scientific-plan packet and atomically switch its pointer."""

    project_root = Path(root)
    science_hash = str(scientific_fingerprint.get("scientific_plan_sha256") or "")
    brief_hash = str(brief.get("brief_semantic_sha256") or "")
    audit_hash = str(audit_fingerprint.get("audit_bundle_sha256") or "")
    presentation_hash = str(presentation_fingerprint.get("presentation_sha256") or "")
    if not science_hash or not brief_hash:
        raise HumanReviewPacketError("A research-plan packet requires scientific and brief semantic identities.")
    if not audit_hash or not presentation_hash:
        raise HumanReviewPacketError("A research-plan packet requires audit and presentation identities.")
    # A packet is an immutable review record.  Scientific identity alone is
    # intentionally insufficient here: an audit refresh of an unchanged plan
    # must create a new, traceable continuity packet instead of overwriting the
    # page that the author previously reviewed.
    packet_id = _safe_packet_id(
        f"research-plan-{science_hash[:20]}-{brief_hash[:8]}-{audit_hash[:12]}-{presentation_hash[:8]}"
    )
    output_dir = _packet_dir(project_root, packet_id)
    packet_relative_dir = _relative(project_root, output_dir)
    existing_packet = _load_json(output_dir / "human_review_packet.json")
    if existing_packet:
        same_identity = (
            existing_packet.get("scientific_plan_sha256") == science_hash
            and existing_packet.get("brief_semantic_sha256") == brief_hash
            and existing_packet.get("audit_bundle_sha256") == audit_hash
            and existing_packet.get("presentation_sha256") == presentation_hash
        )
        if not same_identity:
            raise HumanReviewPacketError(
                "A packet ID collision has conflicting immutable decision identities."
            )
        request = _load_json(output_dir / "confirmation_request.json")
        agent_payload = _load_json(output_dir / "agent_payload.json")
        return {
            "packet": existing_packet,
            "request": request,
            "agent_payload": agent_payload,
            "packet_dir": output_dir,
            "project_relative_dir": packet_relative_dir,
            "primary_human_review_html": agent_payload.get("primary_human_review_html")
            or {
                "project_relative_path": f"{packet_relative_dir}/stage_summary.zh-CN.html",
                "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
                "locale": "zh-CN",
            },
            "secondary_human_review_html": agent_payload.get("secondary_human_review_html")
            or {
                "project_relative_path": f"{packet_relative_dir}/stage_summary.en.html",
                "absolute_path": str((output_dir / "stage_summary.en.html").resolve()),
                "locale": "en",
            },
            "stage_audit_json": agent_payload.get("stage_audit_json")
            or {
                "project_relative_path": f"{packet_relative_dir}/stage_audit.json",
                "absolute_path": str((output_dir / "stage_audit.json").resolve()),
            },
            "reused": True,
        }
    output_dir.mkdir(parents=True, exist_ok=False)
    packet = {
        "schema_version": HUMAN_REVIEW_PACKET_SCHEMA,
        "packet_id": packet_id,
        "decision_family": "scientific_plan",
        "risk_class": "C3",
        "review_state": review_state,
        "review_requirement": review_requirement,
        "decision_status": decision_status,
        "decision_question": brief.get("decision_question_zh"),
        "human_decision_brief_ref": f"{packet_relative_dir}/human_decision_brief_v1.json",
        "scientific_or_effect_fingerprint": f"{packet_relative_dir}/scientific_plan_fingerprint_v1.json",
        "audit_bundle_sha256": audit_hash,
        "presentation_sha256": presentation_hash,
        "semantic_delta": dict(semantic_delta),
        "unresolved_items": unresolved_items,
        "authority": {"actor_type": "user", "policy": "scientific_plan"},
        "expires_when": [
            "research_question",
            "claim_boundary",
            "data_role",
            "cohort",
            "sample_unit",
            "method",
            "statistics",
            "figure_semantics",
            "capability_boundary",
        ],
        "revision_cycle_id": revision_cycle_id,
        "scientific_plan_sha256": science_hash,
        "brief_semantic_sha256": brief_hash,
        "legacy_plan_hash": scientific_fingerprint.get("legacy_plan_hash"),
        "paths": {
            "stage_summary_zh_html": f"{packet_relative_dir}/stage_summary.zh-CN.html",
            "stage_summary_en_html": f"{packet_relative_dir}/stage_summary.en.html",
            "stage_audit_json": f"{packet_relative_dir}/stage_audit.json",
            "artifact_manifest": f"{packet_relative_dir}/artifact_manifest.json",
        },
    }
    request = {
        "schema_version": "dpl.confirmation_request.v2",
        "checkpoint_type": "research_plan",
        "checkpoint_package_id": packet_id,
        "review_state": review_state,
        "review_requirement": review_requirement,
        "decision_status": decision_status,
        "scientific_decision_sha256": science_hash,
        "human_brief_semantic_sha256": brief_hash,
        "confirmation_command": (
            f'draftpaper confirm-research-plan --project "{project_root}" --decision-hash {science_hash}'
        ),
        "allowed": review_state == "confirmable" and decision_status == "pending",
    }
    agent_payload = {
        "schema_version": "dpl.checkpoint_agent_payload.v3",
        "summary_schema": HUMAN_REVIEW_PACKET_SCHEMA,
        "checkpoint_id": packet_id,
        "stage": "research_plan",
        "decision_family": "scientific_plan",
        "primary_human_review_html": {
            "project_relative_path": packet["paths"]["stage_summary_zh_html"],
            "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
            "locale": "zh-CN",
        },
        "secondary_human_review_html": {
            "project_relative_path": packet["paths"]["stage_summary_en_html"],
            "absolute_path": str((output_dir / "stage_summary.en.html").resolve()),
            "locale": "en",
        },
        "stage_audit_json": {
            "project_relative_path": packet["paths"]["stage_audit_json"],
            "absolute_path": str((output_dir / "stage_audit.json").resolve()),
        },
        "technical_audit_json": {
            "project_relative_path": packet["paths"]["stage_audit_json"],
            "absolute_path": str((output_dir / "stage_audit.json").resolve()),
        },
        "stage_completion_summary_zh": str(brief.get("summary_zh") or ""),
        "decision_question_zh": str(brief.get("decision_question_zh") or ""),
        "decision_summary_zh": str(brief.get("summary_zh") or ""),
        "semantic_delta_summary_zh": str(semantic_delta.get("summary_zh") or ""),
        "semantic_delta_summary_en": str(semantic_delta.get("summary_en") or ""),
        "review_points_zh": [str(brief.get("objective_zh") or "")][:1],
        "decision_actor_type": "user",
        "decision_authority_reason_zh": "研究问题、claim、数据、方法、统计和主图合同属于 C3 作者科学决定。",
        "summary_zh": str(brief.get("summary_zh") or ""),
        "semantic_delta": dict(semantic_delta),
        "unresolved_items": unresolved_items[:8],
        "confirmation_meaning_zh": "确认完整研究蓝图后，后续关键图表只能遵守其中的数据、方法、统计和图表合同。",
        "confirmation_meaning_en": "Confirmation freezes the research-plan data, method, statistical, and figure contracts for downstream key-figure work.",
        "scientific_decision_sha256": science_hash,
        "human_brief_semantic_sha256": brief_hash,
        "continuity_status": semantic_delta.get("classification"),
        "latest_user_visible_deliverables": list(brief.get("facts") or [])[:8],
        "confirmation_command": request["confirmation_command"] if request["allowed"] else None,
        "context_budget_bytes": 12 * 1024,
    }
    if len(json.dumps(agent_payload, ensure_ascii=False).encode("utf-8")) > 12 * 1024:
        raise HumanReviewPacketError("Agent review payload exceeds the 12 KB decision-context budget.")
    audit = {
        "schema_version": "dpl.research_plan_stage_audit.v1",
        "packet_id": packet_id,
        "scientific_fingerprint": dict(scientific_fingerprint),
        "audit_fingerprint": dict(audit_fingerprint),
        "presentation_fingerprint": dict(presentation_fingerprint),
        "revision_cycle_id": revision_cycle_id,
        "unresolved_items": unresolved_items,
    }
    manifest = {
        "schema_version": "dpl.checkpoint_artifact_manifest.v2",
        "packet_id": packet_id,
        "artifacts": (audit_fingerprint.get("audit_subject") or {}).get("artifact_records") or [],
    }
    atomic_write_json(output_dir / "human_review_packet.json", packet)
    atomic_write_json(output_dir / "human_decision_brief_v1.json", dict(brief))
    atomic_write_json(output_dir / "scientific_plan_fingerprint_v1.json", dict(scientific_fingerprint))
    atomic_write_json(output_dir / "semantic_diff.json", dict(semantic_delta))
    atomic_write_json(output_dir / "stage_audit.json", audit)
    atomic_write_json(output_dir / "artifact_manifest.json", manifest)
    atomic_write_json(output_dir / "unresolved_issues.json", {"items": unresolved_items})
    atomic_write_json(output_dir / "confirmation_request.json", request)
    atomic_write_json(output_dir / "agent_payload.json", agent_payload)
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", render_zh)
    atomic_write_text(output_dir / "stage_summary.en.html", render_en)
    pointer = {
        "schema_version": "dpl.active_research_plan_review_packet.v1",
        "packet_id": packet_id,
        "packet_path": packet_relative_dir,
        "status": "active" if decision_status not in {"continuity_preserved", "user_confirmed"} else decision_status,
        "scientific_plan_sha256": science_hash,
        "brief_semantic_sha256": brief_hash,
        "audit_bundle_sha256": audit_fingerprint.get("audit_bundle_sha256"),
        "presentation_sha256": presentation_fingerprint.get("presentation_sha256"),
    }
    atomic_write_json(project_root / RESEARCH_PLAN_ACTIVE_POINTER, pointer)
    compat_target = os.path.relpath(output_dir / "stage_summary.zh-CN.html", project_root / "research_plan").replace("\\", "/")
    atomic_write_text(project_root / RESEARCH_PLAN_COMPAT_HTML, _compat_html(compat_target))
    atomic_write_json(
        project_root / RESEARCH_PLAN_COMPAT_JSON,
        {
            "schema_version": "dpl.research_plan_review_packet_compat.v2",
            "active_packet_id": packet_id,
            "packet_path": packet_relative_dir,
            "scientific_plan_sha256": science_hash,
            "brief_semantic_sha256": brief_hash,
        },
    )
    return {
        "packet": packet,
        "request": request,
        "agent_payload": agent_payload,
        "packet_dir": output_dir,
        "project_relative_dir": packet_relative_dir,
        "primary_human_review_html": agent_payload["primary_human_review_html"],
        "secondary_human_review_html": agent_payload["secondary_human_review_html"],
        "stage_audit_json": agent_payload["stage_audit_json"],
        "reused": False,
    }


__all__ = [
    "HUMAN_REVIEW_PACKET_SCHEMA",
    "HumanReviewPacketError",
    "RESEARCH_PLAN_ACTIVE_POINTER",
    "RESEARCH_PLAN_COMPAT_HTML",
    "RESEARCH_PLAN_COMPAT_JSON",
    "active_research_plan_packet",
    "mark_active_research_plan_packet_superseded",
    "write_research_plan_review_packet",
]
