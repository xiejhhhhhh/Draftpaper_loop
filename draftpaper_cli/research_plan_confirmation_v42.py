"""v0.42 research-plan confirmation implementation.

This module is separate from the legacy adapter so existing v1 snapshots can
stay readable. Public functions are re-exported by research_plan_confirmation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from .artifact_identity import canonical_json, sha256_file
from .human_review_packet import (
    RESEARCH_PLAN_ACTIVE_POINTER,
    RESEARCH_PLAN_COMPAT_HTML,
    RESEARCH_PLAN_COMPAT_JSON,
    active_research_plan_packet,
    mark_active_research_plan_packet_superseded,
    write_research_plan_review_packet,
)
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale, update_stage_status
from .research_plan_brief import (
    build_research_plan_decision_brief,
    render_research_plan_decision_html,
    validate_research_plan_decision_brief,
)
from .research_plan_fingerprint import (
    STRUCTURED_PLAN_ARTIFACTS,
    ResearchPlanFingerprintError,
    build_plan_audit_fingerprint,
    build_plan_presentation_fingerprint,
    build_scientific_plan_fingerprint,
    compare_scientific_plan_fingerprints,
    legacy_plan_file_hash,
    read_json_object,
)
from .revision_cycle import (
    begin_revision_cycle,
    close_revision_cycle,
    load_active_revision_cycle,
    update_revision_cycle_review_state,
)
from .state_kernel import append_jsonl_locked, atomic_write_json, atomic_write_text
from .statistical_validation import (
    CONTRACT_JSON as STATISTICAL_CONTRACT,
    COVERAGE_JSON as REVIEW_RULE_COVERAGE,
    assess_review_rule_coverage,
    build_statistical_validation_contract,
)


REQUIRED_MARKER = "research_plan/research_plan_confirmation_required.json"
REVIEW_PACKET_JSON = RESEARCH_PLAN_COMPAT_JSON
REVIEW_PACKET_HTML = RESEARCH_PLAN_COMPAT_HTML
CONFIRMATION_JSON = "research_plan/research_plan_confirmation.json"
SNAPSHOT_JSON = "research_plan/confirmed_research_blueprint_snapshot.json"
HISTORY_DIR = "research_plan/confirmation_history"
DECISION_LEDGER = "research_plan/review_decision_ledger.jsonl"
USER_INTENT_DIR = "research_plan/user_intent_receipts"
MIGRATION_AUDIT_SCHEMA = "dpl.research_plan_migration_audit.v1"
SCIENTIFIC_ARTIFACTS = (
    "research_plan/research_plan.md",
    "research_plan/research_plan.zh-CN.md",
    *STRUCTURED_PLAN_ARTIFACTS,
)


class ResearchPlanConfirmationError(RuntimeError):
    """Raised when a research-plan decision cannot safely continue."""


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    missing: list[str] = []
    records: list[dict[str, Any]] = []
    for relative in SCIENTIFIC_ARTIFACTS:
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        else:
            records.append({"path": relative, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    if missing:
        raise ResearchPlanConfirmationError("Research blueprint is incomplete: " + ", ".join(missing))
    return records


def _inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _read(root / "research_plan" / "pre_execution_support_report.json"),
        _read(root / REVIEW_RULE_COVERAGE),
        _read(root / "research_plan" / "plugin_sufficiency_preview.json"),
    )


def _limitations(
    support: Mapping[str, Any],
    coverage: Mapping[str, Any],
    sufficiency: Mapping[str, Any],
) -> list[str]:
    result: list[str] = []
    decision = str(support.get("decision") or "")
    if decision and decision != "ready_for_confirmation":
        result.append(f"Pre-execution support is {decision}.")
    for family in coverage.get("missing_rule_families") or []:
        result.append(f"Statistical review family {family} currently has no exact mature rule binding.")
    for item in sufficiency.get("rescue_tasks") or []:
        if isinstance(item, Mapping):
            result.append(
                "Capability "
                + str(item.get("requirement_id") or "unknown")
                + " requires "
                + str(item.get("recommended_command") or "a scoped rescue task")
                + "."
            )
    return sorted(dict.fromkeys(result))


def _refresh_cn_plan_projection(root: Path) -> None:
    state = load_project(root)
    blueprint = _read(state.path / "research_plan" / "research_blueprint.json")
    if not blueprint:
        raise ResearchPlanConfirmationError("research_plan/research_blueprint.json is required.")
    from .research_plan import _assert_cn_plan_quality, _render_research_plan_cn
    from .statistical_validation import statistical_plan_summary

    rendered = _render_research_plan_cn(state.metadata, blueprint).rstrip()
    rendered += "\n\n" + statistical_plan_summary(state.path, language="zh-CN")
    _assert_cn_plan_quality(rendered)
    atomic_write_text(state.path / "research_plan" / "research_plan.zh-CN.md", rendered)


def _ensure_cycle(root: Path) -> str | None:
    active = load_active_revision_cycle(root)
    if active and active.get("status") == "open":
        return str(active.get("revision_cycle_id") or "") or None
    try:
        payload = begin_revision_cycle(
            root,
            reason="research_plan_review",
            expected_artifacts=STRUCTURED_PLAN_ARTIFACTS,
            expected_decision_items=(
                "research_objective",
                "claims",
                "figure_storyboard",
                "data_roles",
                "methods",
                "statistics",
                "feasibility_boundary",
            ),
            scope="research_plan",
            started_by="system",
        )
    except Exception:
        return None
    return str((payload.get("revision_cycle") or {}).get("revision_cycle_id") or "") or None


def validate_research_plan_review(project: str | Path) -> dict[str, Any]:
    """Return a fail-closed readiness verdict before a confirmation is created."""

    root = load_project(project).path
    support, coverage, sufficiency = _inputs(root)
    limitations = _limitations(support, coverage, sufficiency)
    fingerprint = build_scientific_plan_fingerprint(
        root,
        feasibility=support,
        review_rule_coverage=coverage,
        limitations=limitations,
    )
    active = load_active_revision_cycle(root)
    pending_tasks = [
        row
        for row in (active or {}).get("pending_tasks") or []
        if not isinstance(row, Mapping) or str(row.get("status") or "pending") not in {"completed", "accepted_limitation"}
    ]
    blockers: list[dict[str, Any]] = []
    if not fingerprint.get("identity_complete"):
        blockers.append(
            {
                "code": "missing_structured_plan_contract",
                "summary_zh": "研究计划缺少结构化科学合同，不能生成确认包。",
                "blocking": True,
                "paths": fingerprint.get("missing_artifacts") or [],
            }
        )
    if pending_tasks:
        blockers.append(
            {
                "code": "revision_cycle_pending_tasks",
                "summary_zh": "本轮研究计划仍有未完成任务；应先完成整轮修订再请求确认。",
                "blocking": True,
                "pending_task_count": len(pending_tasks),
            }
        )
    if support.get("decision") == "blocked_requires_user_route":
        blockers.append(
            {
                "code": "blocked_requires_user_route",
                "summary_zh": "执行前支持需要用户选择补充数据/方法或收窄研究范围。",
                "blocking": True,
            }
        )
    return {
        "status": "blocked" if blockers else "ready_for_review",
        "project_path": str(root),
        "fingerprint": fingerprint,
        "support": support,
        "coverage": coverage,
        "sufficiency": sufficiency,
        "limitations": limitations,
        "unresolved_items": blockers,
        "revision_cycle_id": str((active or {}).get("revision_cycle_id") or "") or None,
    }


def current_plan_hash(project: str | Path) -> str:
    root = load_project(project).path
    support, coverage, sufficiency = _inputs(root)
    fingerprint = build_scientific_plan_fingerprint(
        root,
        feasibility=support,
        review_rule_coverage=coverage,
        limitations=_limitations(support, coverage, sufficiency),
    )
    if not fingerprint.get("identity_complete"):
        raise ResearchPlanConfirmationError(
            "Research blueprint is incomplete: " + ", ".join(fingerprint.get("missing_artifacts") or [])
        )
    return str(fingerprint["scientific_plan_sha256"])


def _latest_user_receipt(root: Path) -> dict[str, Any] | None:
    path = root / DECISION_LEDGER
    if not path.is_file():
        return None
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    for row in reversed(rows):
        if not isinstance(row, Mapping) or row.get("decision_status") != "user_confirmed":
            continue
        expected = _hash({key: value for key, value in row.items() if key not in {"receipt_sha256", "created_at"}})
        if row.get("receipt_sha256") == expected:
            return dict(row)
    return None


def _continuity(
    root: Path,
    fingerprint: Mapping[str, Any],
    brief: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    prior = _latest_user_receipt(root)
    if validation.get("status") != "ready_for_review":
        return {"eligible": False, "classification": "blocked", "previous_receipt": prior}
    if not prior:
        return {"eligible": False, "classification": "first_scientific_decision", "previous_receipt": None}
    if prior.get("scientific_plan_sha256") != fingerprint.get("scientific_plan_sha256"):
        return {"eligible": False, "classification": "scientific_change", "previous_receipt": prior}
    if prior.get("brief_semantic_sha256") != brief.get("brief_semantic_sha256"):
        return {"eligible": False, "classification": "blocked", "previous_receipt": prior}
    return {"eligible": True, "classification": "no_scientific_change", "previous_receipt": prior}


def _write_continuity(output_dir: Path, packet_id: str, fingerprint: Mapping[str, Any], brief: Mapping[str, Any], previous: Mapping[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema_version": "dpl.confirmation_continuity_receipt.v1",
        "receipt_id": "continuity-"
        + _hash(
            {
                "packet": packet_id,
                "science": fingerprint.get("scientific_plan_sha256"),
                "previous": previous.get("receipt_id"),
            }
        )[:20],
        "checkpoint_type": "research_plan",
        "checkpoint_package_id": packet_id,
        "previous_decision_receipt_id": previous.get("receipt_id"),
        "current_scientific_decision_sha256": fingerprint.get("scientific_plan_sha256"),
        "human_brief_semantic_sha256": brief.get("brief_semantic_sha256"),
        "actor_type": "system",
        "actor_id": "draftpaper-cli",
        "decision_effect": "preserve_previous_user_confirmation",
        "semantic_delta_class": "no_scientific_change",
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _hash({key: value for key, value in receipt.items() if key not in {"receipt_sha256", "created_at"}})
    atomic_write_json(output_dir / "confirmation_continuity_receipt.json", receipt)
    return receipt


def mark_research_plan_confirmation_required(project: str | Path) -> dict[str, Any]:
    """Mark a new plan decision without deleting visible historical packets."""

    state = load_project(project)
    active = active_research_plan_packet(state.path)
    marker = {
        "schema_version": "dpl.research_plan_confirmation_required.v2",
        "status": "required",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "reason": "Key-figure code must execute only from a current confirmed scientific plan.",
        "prior_packet_id": (active or {}).get("packet", {}).get("packet_id"),
    }
    _write_json(state.path / REQUIRED_MARKER, marker)
    mark_active_research_plan_packet_superseded(
        state.path,
        reason="A research-plan input changed; the prior review packet remains available for comparison.",
    )
    return marker


def review_research_plan(project: str | Path) -> dict[str, Any]:
    """Create one complete, versioned, bilingual scientific-plan packet."""

    state = load_project(project)
    root = state.path
    if not (root / STATISTICAL_CONTRACT).is_file():
        build_statistical_validation_contract(root)
    if not (root / REVIEW_RULE_COVERAGE).is_file():
        assess_review_rule_coverage(root)
    _refresh_cn_plan_projection(root)
    validation = validate_research_plan_review(root)
    if validation["status"] != "ready_for_review":
        return {
            "status": "refinement_required",
            "project_path": str(root),
            "unresolved_items": validation["unresolved_items"],
            "message": "Complete the current research-plan revision before requesting human confirmation.",
        }
    revision_cycle_id = validation.get("revision_cycle_id") or _ensure_cycle(root)
    if revision_cycle_id:
        try:
            update_revision_cycle_review_state(root, review_status="ready_for_review")
        except Exception:
            # The packet remains valid when a legacy project has no writable
            # revision cycle; its validation result stays the authority.
            pass
    fingerprint = dict(validation["fingerprint"])
    try:
        fingerprint["legacy_plan_hash"] = legacy_plan_file_hash(root)
    except ResearchPlanFingerprintError:
        fingerprint["legacy_plan_hash"] = None
    prior = _latest_user_receipt(root)
    delta = compare_scientific_plan_fingerprints(
        (prior or {}).get("scientific_plan_fingerprint"),
        fingerprint,
    )
    brief = build_research_plan_decision_brief(
        project_metadata=state.metadata,
        fingerprint=fingerprint,
        semantic_delta=delta,
        limitations=validation["limitations"],
        pre_execution_decision=str(validation["support"].get("decision") or ""),
        review_rule_decision=str(validation["coverage"].get("decision") or ""),
    )
    issues = validate_research_plan_decision_brief(brief)
    if issues:
        return {
            "status": "blocked",
            "project_path": str(root),
            "unresolved_items": [
                {"code": "research_plan_brief_contract", "summary_zh": issue, "blocking": True}
                for issue in issues
            ],
        }
    audit = build_plan_audit_fingerprint(
        root,
        validation={"status": validation["status"], "revision_cycle_id": revision_cycle_id},
    )
    presentation = build_plan_presentation_fingerprint(brief)
    continuity = _continuity(root, fingerprint, brief, validation)
    decision_status = "continuity_preserved" if continuity["eligible"] else "pending"
    requirement = "notify_only" if continuity["eligible"] else "human_required"
    packet_dir = root / "review" / "checkpoints" / (
        "research-plan-" + str(fingerprint["scientific_plan_sha256"])[:20] + "-" + str(brief["brief_semantic_sha256"])[:8]
    )
    written = write_research_plan_review_packet(
        root,
        brief=brief,
        scientific_fingerprint=fingerprint,
        audit_fingerprint=audit,
        presentation_fingerprint=presentation,
        semantic_delta=delta,
        review_state="confirmable",
        review_requirement=requirement,
        decision_status=decision_status,
        unresolved_items=[],
        revision_cycle_id=revision_cycle_id,
        render_zh=render_research_plan_decision_html(root, packet_dir, brief, locale="zh-CN"),
        render_en=render_research_plan_decision_html(root, packet_dir, brief, locale="en"),
    )
    compatibility = _read(root / REVIEW_PACKET_JSON)
    compatibility.update(
        {
            "plan_hash": fingerprint["scientific_plan_sha256"],
            "decision_hash": fingerprint["scientific_plan_sha256"],
            "confirmation_requires_accept_limitations": bool(validation["limitations"]),
            "limitations": validation["limitations"],
            "status": decision_status,
        }
    )
    atomic_write_json(root / REVIEW_PACKET_JSON, compatibility)
    if continuity["eligible"] and not written.get("reused"):
        _write_continuity(
            Path(written["packet_dir"]),
            str(written["packet"]["packet_id"]),
            fingerprint,
            brief,
            dict(continuity["previous_receipt"]),
        )
        pointer = _read(root / RESEARCH_PLAN_ACTIVE_POINTER)
        pointer["status"] = "continuity_preserved"
        pointer["continuity_receipt"] = str((Path(written["packet_dir"]) / "confirmation_continuity_receipt.json").relative_to(root).as_posix())
        atomic_write_json(root / RESEARCH_PLAN_ACTIVE_POINTER, pointer)
    elif continuity["eligible"] and written.get("reused"):
        # The old user decision already binds this exact immutable packet.
        # Reusing it is a notification, not a new decision or packet write.
        active = active_research_plan_packet(root)
        if active and active.get("packet", {}).get("packet_id") == written["packet"].get("packet_id"):
            pointer = _read(root / RESEARCH_PLAN_ACTIVE_POINTER)
            pointer.setdefault("status", "user_confirmed")
            atomic_write_json(root / RESEARCH_PLAN_ACTIVE_POINTER, pointer)
    return {
        "status": "continuity_preserved" if continuity["eligible"] else "ready_for_human_review",
        "project_path": str(root),
        "plan_hash": fingerprint["scientific_plan_sha256"],
        "decision_hash": fingerprint["scientific_plan_sha256"],
        "legacy_plan_hash": fingerprint.get("legacy_plan_hash"),
        "review_packet": REVIEW_PACKET_HTML,
        "review_packet_json": REVIEW_PACKET_JSON,
        "packet_id": written["packet"]["packet_id"],
        "primary_human_review_html": written["primary_human_review_html"],
        "secondary_human_review_html": written["secondary_human_review_html"],
        "stage_audit_json": written["stage_audit_json"],
        "limitations": validation["limitations"],
        "confirmation_requires_accept_limitations": bool(validation["limitations"]),
        "confirmation_continuity": continuity,
        "confirmation_command": written["request"].get("confirmation_command"),
    }


def confirm_research_plan(
    project: str | Path,
    *,
    plan_hash: str | None = None,
    decision_hash: str | None = None,
    accept_limitations: bool = False,
) -> dict[str, Any]:
    root = load_project(project).path
    active = active_research_plan_packet(root)
    if not active:
        raise ResearchPlanConfirmationError("Run review-research-plan before confirmation.")
    packet = active["packet"]
    packet_dir = Path(active["packet_dir"])
    if packet.get("review_state") != "confirmable":
        raise ResearchPlanConfirmationError("The active research-plan packet is not confirmable.")
    if packet.get("decision_status") == "continuity_preserved":
        return {
            "status": "continuity_preserved",
            "project_path": str(root),
            "packet_id": packet.get("packet_id"),
            "confirmed_plan_hash": packet.get("scientific_plan_sha256"),
        }
    supplied = str(decision_hash or plan_hash or "")
    current = current_plan_hash(root)
    if supplied != current or packet.get("scientific_plan_sha256") != current:
        raise ResearchPlanConfirmationError("The supplied decision hash does not match the active scientific plan.")
    brief = _read(packet_dir / "human_decision_brief_v1.json")
    if not brief:
        raise ResearchPlanConfirmationError("The active packet lacks a decision brief.")
    if brief.get("limitations") and not accept_limitations:
        raise ResearchPlanConfirmationError("The review packet contains explicit limitations; confirmation requires --accept-limitations.")
    support, coverage, sufficiency = _inputs(root)
    if support.get("decision") == "blocked_requires_user_route":
        raise ResearchPlanConfirmationError("Pre-execution support is blocked; choose a route before confirmation.")
    fingerprint = build_scientific_plan_fingerprint(
        root,
        feasibility=support,
        review_rule_coverage=coverage,
        limitations=_limitations(support, coverage, sufficiency),
    )
    if fingerprint.get("scientific_plan_sha256") != current:
        raise ResearchPlanConfirmationError("The scientific plan changed while this packet was open.")
    embedded: dict[str, Any] = {}
    for relative in SCIENTIFIC_ARTIFACTS:
        path = root / relative
        if path.suffix.lower() == ".json":
            embedded[relative] = _read(path)
        elif path.is_file():
            embedded[relative] = path.read_text(encoding="utf-8-sig")
    snapshot_id = current[:20]
    snapshot = {
        "schema_version": "dpl.confirmed_research_blueprint_snapshot.v2",
        "status": "confirmed",
        "active": True,
        "confirmed_at": utc_now(),
        "project_id": load_project(root).metadata.get("project_id"),
        "snapshot_id": snapshot_id,
        "confirmed_plan_hash": current,
        "scientific_plan_sha256": current,
        "brief_semantic_sha256": brief.get("brief_semantic_sha256"),
        "review_packet_id": packet.get("packet_id"),
        "scientific_plan_fingerprint": fingerprint,
        "artifacts": _artifact_records(root),
        "embedded_contracts": embedded,
        "accepted_limitations": brief.get("limitations") if accept_limitations else [],
        "execution_policy": "Key figures and panels must match this snapshot exactly; implementation repair cannot change scientific semantics.",
    }
    receipt = {
        "schema_version": "dpl.research_plan_decision_receipt.v1",
        "receipt_id": "research-plan-" + uuid.uuid4().hex,
        "decision_status": "user_confirmed",
        "actor_type": "user",
        "actor_id": "user",
        "packet_id": packet.get("packet_id"),
        "scientific_plan_sha256": current,
        "brief_semantic_sha256": brief.get("brief_semantic_sha256"),
        "scientific_plan_fingerprint": fingerprint,
        "accepted_limitations": bool(accept_limitations),
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _hash({key: value for key, value in receipt.items() if key not in {"receipt_sha256", "created_at"}})
    atomic_write_json(root / SNAPSHOT_JSON, snapshot)
    atomic_write_json(
        root / CONFIRMATION_JSON,
        {
            "schema_version": "dpl.research_plan_confirmation.v2",
            "status": "approved",
            "confirmed_at": snapshot["confirmed_at"],
            "snapshot_id": snapshot_id,
            "plan_hash": current,
            "decision_hash": current,
            "packet_id": packet.get("packet_id"),
            "accepted_limitations": bool(accept_limitations),
        },
    )
    append_jsonl_locked(root / DECISION_LEDGER, receipt)
    atomic_write_json(packet_dir / "review_decision_receipt.json", receipt)
    pointer = _read(root / RESEARCH_PLAN_ACTIVE_POINTER)
    pointer.update(
        {
            "status": "user_confirmed",
            "receipt_path": str((packet_dir / "review_decision_receipt.json").relative_to(root).as_posix()),
        }
    )
    atomic_write_json(root / RESEARCH_PLAN_ACTIVE_POINTER, pointer)
    # A user-confirmed decision completes the research-plan stage itself.
    # Without this transition the stage remains stale after a scoped reopen,
    # and the workflow incorrectly recommends regenerating an already
    # immutable, human-confirmed plan.
    update_stage_status(root, "research_plan", "approved")
    active_cycle = load_active_revision_cycle(root)
    if active_cycle and active_cycle.get("status") == "open":
        try:
            close_revision_cycle(root, decision_receipt_id=receipt["receipt_id"], status="closed")
        except Exception:
            pass
    return {
        "status": "approved",
        "project_path": str(root),
        "snapshot_id": snapshot_id,
        "confirmed_plan_hash": current,
        "decision_hash": current,
        "packet_id": packet.get("packet_id"),
        "snapshot": SNAPSHOT_JSON,
        "receipt": receipt,
    }


def confirmation_state(project: str | Path) -> dict[str, Any]:
    root = load_project(project).path
    marker = root / REQUIRED_MARKER
    snapshot = _read(root / SNAPSHOT_JSON)
    if not marker.exists() and not snapshot:
        return {"required": False, "status": "legacy_not_required", "current": True}
    if not snapshot or not snapshot.get("active"):
        return {"required": True, "status": "awaiting_confirmation", "current": False}
    try:
        current = current_plan_hash(root)
    except ResearchPlanConfirmationError as exc:
        return {"required": True, "status": "incomplete", "current": False, "reason": str(exc)}
    matches = current == snapshot.get("scientific_plan_sha256", snapshot.get("confirmed_plan_hash"))
    return {
        "required": True,
        "status": "confirmed" if matches else "scientific_contract_drift",
        "current": matches,
        "confirmed_plan_hash": snapshot.get("confirmed_plan_hash"),
        "current_plan_hash": current,
        "snapshot_id": snapshot.get("snapshot_id"),
    }


def require_confirmed_research_blueprint(project: str | Path) -> dict[str, Any]:
    state = confirmation_state(project)
    if state["required"] and not state["current"]:
        raise ResearchPlanConfirmationError(
            "Key-figure execution requires the current human-confirmed research blueprint. Run review-research-plan and confirm-research-plan."
        )
    return _read(load_project(project).path / SNAPSHOT_JSON) if state["required"] else {}


def _intent(root: Path, reason: str) -> tuple[dict[str, Any], Path]:
    receipt = {
        "schema_version": "dpl.user_intent_receipt.v1",
        "receipt_id": "intent-" + uuid.uuid4().hex,
        "decision_family": "scientific_plan",
        "intent": "reopen_research_plan",
        "actor_type": "user",
        "actor_id": "user",
        "reason": reason,
        "created_at": utc_now(),
    }
    receipt["receipt_sha256"] = _hash({key: value for key, value in receipt.items() if key not in {"receipt_sha256", "created_at"}})
    path = root / USER_INTENT_DIR / f"{receipt['receipt_id']}.json"
    atomic_write_json(path, receipt)
    return receipt, path


def reopen_research_plan(project: str | Path, *, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise ResearchPlanConfirmationError("A reason is required to reopen the research plan.")
    root = load_project(project).path
    snapshot_path = root / SNAPSHOT_JSON
    snapshot = _read(snapshot_path)
    if not snapshot:
        raise ResearchPlanConfirmationError("No active confirmed research blueprint exists.")
    history = root / HISTORY_DIR
    history.mkdir(parents=True, exist_ok=True)
    archive = history / f"{snapshot.get('snapshot_id') or 'snapshot'}_{utc_now().replace(':', '').replace('-', '')}.json"
    shutil.copy2(snapshot_path, archive)
    snapshot_path.unlink()
    _, intent_path = _intent(root, str(reason).strip())
    mark_active_research_plan_packet_superseded(root, reason=str(reason).strip())
    confirmation = {
        "schema_version": "dpl.research_plan_confirmation.v2",
        "status": "reopened",
        "reopened_at": utc_now(),
        "previous_snapshot_id": snapshot.get("snapshot_id"),
        "reason": str(reason).strip(),
        "history_snapshot": archive.relative_to(root).as_posix(),
        "user_intent_receipt": intent_path.relative_to(root).as_posix(),
    }
    atomic_write_json(root / CONFIRMATION_JSON, confirmation)
    marker = mark_research_plan_confirmation_required(root)
    marker["user_intent_receipt"] = confirmation["user_intent_receipt"]
    atomic_write_json(root / REQUIRED_MARKER, marker)
    _ensure_cycle(root)
    mark_stage_stale(root, "research_plan", include_self=False)
    return {
        "status": "reopened",
        "project_path": str(root),
        "previous_snapshot_id": snapshot.get("snapshot_id"),
        "history_snapshot": confirmation["history_snapshot"],
        "user_intent_receipt": confirmation["user_intent_receipt"],
        "reason": confirmation["reason"],
    }


def show_research_plan_review_packet(project: str | Path) -> dict[str, Any]:
    root = load_project(project).path
    active = active_research_plan_packet(root)
    if not active:
        return {"status": "not_found", "project_path": str(root)}
    packet_dir = Path(active["packet_dir"])
    packet = active["packet"]
    return {
        "status": "passed",
        "project_path": str(root),
        "packet_id": packet.get("packet_id"),
        "decision_status": packet.get("decision_status"),
        "review_state": packet.get("review_state"),
        "primary_human_review_html": {
            "project_relative_path": str((packet_dir / "stage_summary.zh-CN.html").relative_to(root).as_posix()),
            "absolute_path": str((packet_dir / "stage_summary.zh-CN.html").resolve()),
        },
        "secondary_human_review_html": {
            "project_relative_path": str((packet_dir / "stage_summary.en.html").relative_to(root).as_posix()),
            "absolute_path": str((packet_dir / "stage_summary.en.html").resolve()),
        },
        "stage_audit_json": {
            "project_relative_path": str((packet_dir / "stage_audit.json").relative_to(root).as_posix()),
            "absolute_path": str((packet_dir / "stage_audit.json").resolve()),
        },
    }


def compare_research_plan_decision(project: str | Path, *, against: str = "latest-confirmed") -> dict[str, Any]:
    root = load_project(project).path
    active = active_research_plan_packet(root)
    if not active:
        return {"status": "not_found", "project_path": str(root)}
    packet_dir = Path(active["packet_dir"])
    return {
        "status": "passed",
        "project_path": str(root),
        "against": against,
        "packet_id": active["packet"].get("packet_id"),
        "semantic_delta": _read(packet_dir / "semantic_diff.json"),
    }


def explain_research_plan_reconfirmation(project: str | Path) -> dict[str, Any]:
    comparison = compare_research_plan_decision(project)
    delta = comparison.get("semantic_delta") or {}
    return {
        **comparison,
        "requires_user_confirmation": delta.get("classification") not in {"no_scientific_change"},
        "reason": delta.get("summary_zh"),
    }


def audit_research_plan_migration(project: str | Path) -> dict[str, Any]:
    """Read a prior plan snapshot without promoting it into a new decision.

    A historical file hash alone never proves that an author saw the current
    DecisionBrief.  This audit therefore reports continuity as eligible only
    when the current semantic projection matches *and* an already-valid,
    hash-bound user receipt exists.  It writes no marker, receipt, packet, or
    project-state file.
    """

    root = load_project(project).path
    snapshot_path = root / SNAPSHOT_JSON
    if not snapshot_path.is_file():
        return {
            "schema_version": MIGRATION_AUDIT_SCHEMA,
            "status": "not_found",
            "project_path": str(root),
            "source_files_mutated": False,
        }
    before = sha256_file(snapshot_path)
    snapshot = _read(snapshot_path)
    support, coverage, sufficiency = _inputs(root)
    limitations = _limitations(support, coverage, sufficiency)
    current = build_scientific_plan_fingerprint(
        root,
        feasibility=support,
        review_rule_coverage=coverage,
        limitations=limitations,
    )
    source_schema = str(snapshot.get("schema_version") or "")
    source_fingerprint = snapshot.get("scientific_plan_fingerprint")
    result: dict[str, Any] = {
        "schema_version": MIGRATION_AUDIT_SCHEMA,
        "project_path": str(root),
        "source_snapshot_path": SNAPSHOT_JSON,
        "source_snapshot_schema": source_schema or "unknown",
        "source_snapshot_sha256": before,
        "current_scientific_plan_sha256": current.get("scientific_plan_sha256"),
        "source_files_mutated": False,
        "source_snapshot_unchanged": before == sha256_file(snapshot_path),
    }
    if not isinstance(source_fingerprint, Mapping):
        return {
            **result,
            "status": "legacy_read_only",
            "migration_action": "create_one_v42_research_plan_packet_and_request_c3",
            "reason_codes": ["legacy_snapshot_has_no_structured_scientific_fingerprint"],
        }
    delta = compare_scientific_plan_fingerprints(source_fingerprint, current)
    latest = _latest_user_receipt(root)
    source_brief = str(snapshot.get("brief_semantic_sha256") or "")
    receipt_matches = bool(
        latest
        and latest.get("scientific_plan_sha256") == current.get("scientific_plan_sha256")
        and source_brief
        and latest.get("brief_semantic_sha256") == source_brief
    )
    if delta.get("classification") == "no_scientific_change" and current.get("identity_complete") and receipt_matches:
        return {
            **result,
            "status": "continuity_eligible",
            "migration_action": "reuse_existing_valid_receipt_without_rewriting_snapshot",
            "reason_codes": [],
            "semantic_delta": delta,
            "receipt_id": latest.get("receipt_id"),
        }
    reasons = []
    if delta.get("classification") != "no_scientific_change":
        reasons.append("scientific_plan_changed_or_unknown")
    if not current.get("identity_complete"):
        reasons.append("current_scientific_identity_incomplete")
    if not receipt_matches:
        reasons.append("no_matching_hash_bound_user_receipt")
    return {
        **result,
        "status": "reconfirmation_required",
        "migration_action": "create_one_v42_research_plan_packet_and_request_c3",
        "reason_codes": reasons,
        "semantic_delta": delta,
    }


__all__ = [
    "CONFIRMATION_JSON",
    "DECISION_LEDGER",
    "HISTORY_DIR",
    "REQUIRED_MARKER",
    "REVIEW_PACKET_HTML",
    "REVIEW_PACKET_JSON",
    "SCIENTIFIC_ARTIFACTS",
    "SNAPSHOT_JSON",
    "ResearchPlanConfirmationError",
    "MIGRATION_AUDIT_SCHEMA",
    "audit_research_plan_migration",
    "compare_research_plan_decision",
    "confirm_research_plan",
    "confirmation_state",
    "current_plan_hash",
    "explain_research_plan_reconfirmation",
    "mark_research_plan_confirmation_required",
    "reopen_research_plan",
    "require_confirmed_research_blueprint",
    "review_research_plan",
    "show_research_plan_review_packet",
    "validate_research_plan_review",
]
