"""Human review, confirmation snapshots, and explicit research-plan reopen."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .pre_execution_support import REPORT_JSON as PRE_EXECUTION_REPORT, assess_pre_execution_support
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale
from .statistical_validation import (
    CONTRACT_JSON as STATISTICAL_CONTRACT,
    COVERAGE_JSON as REVIEW_RULE_COVERAGE,
    assess_review_rule_coverage,
    build_statistical_validation_contract,
)


REQUIRED_MARKER = "research_plan/research_plan_confirmation_required.json"
REVIEW_PACKET_JSON = "research_plan/research_plan_review_packet.json"
REVIEW_PACKET_HTML = "research_plan/research_plan_review_packet.html"
CONFIRMATION_JSON = "research_plan/research_plan_confirmation.json"
SNAPSHOT_JSON = "research_plan/confirmed_research_blueprint_snapshot.json"
HISTORY_DIR = "research_plan/confirmation_history"

SCIENTIFIC_ARTIFACTS = [
    "research_plan/research_plan.md",
    "research_plan/research_plan.zh-CN.md",
    "research_plan/research_blueprint.json",
    "research_plan/claim_contract.json",
    "research_plan/figure_storyboard.json",
    "research_plan/method_plan.json",
    "research_plan/discipline_contract.json",
    "research_plan/research_capability_contract.json",
    STATISTICAL_CONTRACT,
]


class ResearchPlanConfirmationError(RuntimeError):
    """Raised when key-figure execution lacks a current human-confirmed plan."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_records(project_path: Path) -> list[dict[str, Any]]:
    records = []
    missing = []
    for relative in SCIENTIFIC_ARTIFACTS:
        path = project_path / relative
        if not path.exists():
            missing.append(relative)
            continue
        records.append({"path": relative, "sha256": _sha256(path), "size_bytes": path.stat().st_size})
    if missing:
        raise ResearchPlanConfirmationError("Research blueprint is incomplete: " + ", ".join(missing))
    return records


def current_plan_hash(project: str | Path) -> str:
    state = load_project(project)
    records = _artifact_records(state.path)
    encoded = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def mark_research_plan_confirmation_required(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    marker = {
        "schema_version": "dpl.research_plan_confirmation_required.v1",
        "status": "required",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "reason": "Key-figure code must execute only from a human-confirmed research blueprint and feasibility packet.",
    }
    _write_json(state.path / REQUIRED_MARKER, marker)
    for relative in (SNAPSHOT_JSON, CONFIRMATION_JSON, REVIEW_PACKET_JSON, REVIEW_PACKET_HTML):
        path = state.path / relative
        if path.exists():
            path.unlink()
    return marker


def _render_review_packet(packet: dict[str, Any]) -> str:
    lines = [
        "# 研究蓝图与可行性确认",
        "",
        "本确认授权 Draftpaper-loop 严格按照当前研究蓝图生成关键图表。确认后，Agent 只能补齐实现，不能自行更换数据角色、方法、统计设计、主图或 panel。",
        "",
        f"Plan hash: `{packet['plan_hash']}`",
        "",
        "## 需要人工确认的内容",
        "",
        "- 研究问题、claim 和论断边界是否正确。",
        "- 中文研究方案是否准确表达用户的科研意图。",
        "- 每个主图组和 panel 是否必要且共同构成完整科学故事。",
        "- 数据、方法、统计验证和能力缺口是否可接受。",
        "- 若有不正确内容，应先人工纠错并生成新的 plan hash，而不是继续执行。",
        "",
        "## 主要文件",
        "",
        "- [中文版研究方案](research_plan.zh-CN.md)",
        "- [英文研究方案](research_plan.md)",
        "- Statistical validation: `statistical_validation_contract.md`",
        "- Pre-execution support: `pre_execution_support_report.html`",
        "",
        f"Pre-execution decision: `{packet['pre_execution_support_decision']}`",
        "",
        f"Review-rule coverage: `{packet['review_rule_coverage_decision']}`",
        "",
    ]
    if packet.get("limitations"):
        lines.extend(["## 待接受或修复的限制", ""])
        lines.extend(f"- {item}" for item in packet["limitations"])
    return "\n".join(lines)


def review_research_plan(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    if not (state.path / STATISTICAL_CONTRACT).exists():
        build_statistical_validation_contract(state.path)
    if not (state.path / REVIEW_RULE_COVERAGE).exists():
        assess_review_rule_coverage(state.path)
    support = assess_pre_execution_support(state.path)
    coverage = _read_json(state.path / REVIEW_RULE_COVERAGE)
    sufficiency = _read_json(state.path / "research_plan" / "plugin_sufficiency_preview.json")
    plan_hash = current_plan_hash(state.path)
    limitations = []
    if support.get("decision") != "ready_for_confirmation":
        limitations.append(f"Pre-execution support is {support.get('decision')}.")
    for family in coverage.get("missing_rule_families") or []:
        limitations.append(f"Statistical review family `{family}` currently has no exact mature rule binding.")
    for item in sufficiency.get("rescue_tasks") or []:
        limitations.append(f"Capability `{item.get('requirement_id')}` requires {item.get('recommended_command')}.")
    packet = {
        "schema_version": "dpl.research_plan_review_packet.v1",
        "status": "ready_for_human_review",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "plan_hash": plan_hash,
        "artifacts": _artifact_records(state.path),
        "pre_execution_support_decision": support.get("decision"),
        "review_rule_coverage_decision": coverage.get("decision"),
        "limitations": limitations,
        "confirmation_requires_accept_limitations": bool(limitations),
        "confirmation_semantics": "Approve the scientific blueprint, feasibility boundary, figure storyboard, and statistical plan; do not merely approve file presence.",
    }
    _write_json(state.path / REVIEW_PACKET_JSON, packet)
    write_html_report(state.path / REVIEW_PACKET_HTML, _render_review_packet(packet), title="研究蓝图与可行性确认")
    return {"status": "ready_for_human_review", "project_path": str(state.path), "plan_hash": plan_hash, "review_packet": REVIEW_PACKET_HTML, "limitations": limitations, "confirmation_requires_accept_limitations": bool(limitations)}


def confirm_research_plan(project: str | Path, *, plan_hash: str, accept_limitations: bool = False) -> dict[str, Any]:
    state = load_project(project)
    packet = _read_json(state.path / REVIEW_PACKET_JSON)
    if not packet:
        raise ResearchPlanConfirmationError("Run review-research-plan before confirmation.")
    current = current_plan_hash(state.path)
    if plan_hash != current or packet.get("plan_hash") != current:
        raise ResearchPlanConfirmationError("The supplied plan hash does not match the current research blueprint.")
    support_decision = str(packet.get("pre_execution_support_decision") or "")
    if support_decision == "blocked_requires_user_route":
        raise ResearchPlanConfirmationError("Pre-execution support is blocked; choose supplement or research-scope revision first.")
    if packet.get("confirmation_requires_accept_limitations") and not accept_limitations:
        raise ResearchPlanConfirmationError("The review packet contains explicit limitations; confirmation requires --accept-limitations.")
    embedded: dict[str, Any] = {}
    for record in packet.get("artifacts") or []:
        relative = str(record["path"])
        path = state.path / relative
        if path.suffix.lower() == ".json":
            embedded[relative] = _read_json(path)
        else:
            embedded[relative] = path.read_text(encoding="utf-8-sig")
    snapshot_id = plan_hash[:20]
    snapshot = {
        "schema_version": "dpl.confirmed_research_blueprint_snapshot.v1",
        "status": "confirmed",
        "active": True,
        "confirmed_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "snapshot_id": snapshot_id,
        "confirmed_plan_hash": plan_hash,
        "artifacts": packet.get("artifacts") or [],
        "embedded_contracts": embedded,
        "accepted_limitations": packet.get("limitations") if accept_limitations else [],
        "execution_policy": "Key figures and panels must match this snapshot exactly; implementation repair cannot change scientific semantics.",
    }
    confirmation = {
        "schema_version": "dpl.research_plan_confirmation.v1",
        "status": "approved",
        "confirmed_at": snapshot["confirmed_at"],
        "project_id": state.metadata.get("project_id"),
        "snapshot_id": snapshot_id,
        "plan_hash": plan_hash,
        "accepted_limitations": bool(accept_limitations),
    }
    _write_json(state.path / SNAPSHOT_JSON, snapshot)
    _write_json(state.path / CONFIRMATION_JSON, confirmation)
    return {"status": "approved", "project_path": str(state.path), "snapshot_id": snapshot_id, "confirmed_plan_hash": plan_hash, "snapshot": SNAPSHOT_JSON}


def confirmation_state(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    marker = state.path / REQUIRED_MARKER
    if not marker.exists():
        return {"required": False, "status": "legacy_not_required", "current": True}
    snapshot = _read_json(state.path / SNAPSHOT_JSON)
    if not snapshot or not snapshot.get("active"):
        return {"required": True, "status": "awaiting_confirmation", "current": False}
    try:
        current = current_plan_hash(state.path)
    except ResearchPlanConfirmationError as exc:
        return {"required": True, "status": "incomplete", "current": False, "reason": str(exc)}
    matches = current == snapshot.get("confirmed_plan_hash")
    return {"required": True, "status": "confirmed" if matches else "scientific_contract_drift", "current": matches, "confirmed_plan_hash": snapshot.get("confirmed_plan_hash"), "current_plan_hash": current, "snapshot_id": snapshot.get("snapshot_id")}


def require_confirmed_research_blueprint(project: str | Path) -> dict[str, Any]:
    state = confirmation_state(project)
    if state["required"] and not state["current"]:
        raise ResearchPlanConfirmationError(
            "Key-figure execution requires the current human-confirmed research blueprint. Run review-research-plan and confirm-research-plan."
        )
    project_path = load_project(project).path
    return _read_json(project_path / SNAPSHOT_JSON) if state["required"] else {}


def reopen_research_plan(project: str | Path, *, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise ResearchPlanConfirmationError("A reason is required to reopen the research plan.")
    state = load_project(project)
    snapshot_path = state.path / SNAPSHOT_JSON
    snapshot = _read_json(snapshot_path)
    if not snapshot:
        raise ResearchPlanConfirmationError("No active confirmed research blueprint exists.")
    history = state.path / HISTORY_DIR
    history.mkdir(parents=True, exist_ok=True)
    archive = history / f"{snapshot.get('snapshot_id') or 'snapshot'}_{utc_now().replace(':', '').replace('-', '')}.json"
    shutil.copy2(snapshot_path, archive)
    snapshot_path.unlink()
    confirmation = {
        "schema_version": "dpl.research_plan_confirmation.v1",
        "status": "reopened",
        "reopened_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "previous_snapshot_id": snapshot.get("snapshot_id"),
        "reason": str(reason).strip(),
        "history_snapshot": archive.relative_to(state.path).as_posix(),
    }
    _write_json(state.path / CONFIRMATION_JSON, confirmation)
    mark_stage_stale(state.path, "research_plan", include_self=False)
    return {"status": "reopened", "project_path": str(state.path), "previous_snapshot_id": snapshot.get("snapshot_id"), "history_snapshot": confirmation["history_snapshot"], "reason": confirmation["reason"]}
