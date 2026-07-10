# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .passport import utc_now
from .project_scaffold import _write_json
from .project_state import load_project, mark_stages_stale, update_stage_status


CLAIM_CONTRACT_JSON = "research_plan/claim_contract.json"
CLAIM_DOWNGRADE_DECISION_JSON = "research_plan/claim_downgrade_decision.json"
RESULT_EVIDENCE_FREEZE_JSON = "results/result_evidence_freeze.json"

DOWNGRADE_STALE_STAGES = [
    "results",
    "introduction",
    "data_writing",
    "methods_writing",
    "discussion",
    "latex",
    "quality_checks",
]


class ClaimContractError(RuntimeError):
    """Raised when a claim contract or downgrade route cannot be applied."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _compact(text: Any, limit: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _claim_strength(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["outperform", "improve", "superior", "robust", "significant", "higher than"]):
        return "strong"
    if any(token in lowered for token in ["exploratory", "limited", "suggest", "boundary", "descriptive"]):
        return "exploratory"
    return "moderate"


def _claim_from_blueprint_claim(item: dict[str, Any], index: int) -> dict[str, Any]:
    claim_id = str(item.get("claim_id") or f"claim_{index}")
    planned = _compact(item.get("expected_finding") or item.get("claim_text") or item.get("research_question"))
    return {
        "claim_id": claim_id,
        "planned_claim": planned,
        "active_claim": planned,
        "original_strength": _claim_strength(planned),
        "active_strength": _claim_strength(planned),
        "research_question": _compact(item.get("research_question")),
        "linked_figures": [],
        "linked_metrics": [],
        "required_evidence_roles": [],
        "claim_boundary": "Use this claim only within the verified data, method, validation, and figure-evidence limits.",
        "status": "planned",
    }


def build_claim_contract_from_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Build the manuscript-facing claim contract from the research blueprint."""
    raw_claims = [item for item in blueprint.get("research_claims") or [] if isinstance(item, dict)]
    claims = [_claim_from_blueprint_claim(item, index) for index, item in enumerate(raw_claims, start=1)]
    by_id = {claim["claim_id"]: claim for claim in claims}
    for figure in (blueprint.get("figure_storyboard") or {}).get("figures") or []:
        if not isinstance(figure, dict):
            continue
        figure_id = str(figure.get("figure_id") or "")
        claim_id = str(figure.get("claim_id") or "")
        if not claim_id:
            research_question = str(figure.get("research_question") or "")
            claim = next((item for item in claims if item.get("research_question") == _compact(research_question)), None)
        else:
            claim = by_id.get(claim_id)
        if claim is None:
            index = len(claims) + 1
            claim = _claim_from_blueprint_claim({
                "claim_id": str(figure.get("claim_id") or figure_id or f"claim_{index}"),
                "expected_finding": figure.get("expected_finding"),
                "research_question": figure.get("research_question"),
            }, index)
            claims.append(claim)
            by_id[claim["claim_id"]] = claim
        if figure_id and figure_id not in claim["linked_figures"]:
            claim["linked_figures"].append(figure_id)
        metric = str(figure.get("validation_metric") or "").strip()
        if metric and metric not in claim["linked_metrics"]:
            claim["linked_metrics"].append(metric)
        for role in figure.get("required_data") or []:
            value = str(role)
            if value not in claim["required_evidence_roles"]:
                claim["required_evidence_roles"].append(value)
    return {
        "status": "written",
        "schema_version": "v0.18.2",
        "generated_at": utc_now(),
        "source": "research_blueprint",
        "project_id": blueprint.get("project_id"),
        "title": blueprint.get("title"),
        "route_state": "planned",
        "claims": claims,
        "downgrade_policy": {
            "allowed": True,
            "rule": "When results are valid but weaker than planned, keep current figures and metrics frozen and lower active claims instead of regenerating results.",
        },
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze_result_artifacts(project_path: Path, *, route: str) -> dict[str, Any]:
    relatives = [
        "results/result_manifest.yaml",
        "results/result_validity_report.json",
        "results/resolved_result_evidence.json",
        "methods/run_manifest.yaml",
    ]
    artifact_hashes = {
        relative: _hash_file(project_path / relative)
        for relative in relatives
        if (project_path / relative).is_file()
    }
    for figure in sorted((project_path / "results" / "figures").glob("*")):
        if figure.is_file():
            artifact_hashes[figure.relative_to(project_path).as_posix()] = _hash_file(figure)
    version_seed = json.dumps({"route": route, "artifacts": artifact_hashes}, ensure_ascii=True, sort_keys=True)
    freeze_id = hashlib.sha256(version_seed.encode("utf-8")).hexdigest()[:20]
    archive_relative = f"results/evidence_snapshots/result_freeze_{freeze_id}.json"
    payload = {
        "status": "frozen",
        "schema_version": "v0.18.4",
        "freeze_id": freeze_id,
        "route": route,
        "frozen_at": utc_now(),
        "policy": "Current figures, tables, run manifests, and metrics are frozen; no result rerun is performed by the downgrade route.",
        "artifact_count": len(artifact_hashes),
        "artifacts": artifact_hashes,
        "versioned_snapshot": archive_relative,
    }
    _write_json(project_path / RESULT_EVIDENCE_FREEZE_JSON, payload)
    archive_path = project_path / archive_relative
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(archive_path, payload)
    return payload


def _downgrade_text(claim: dict[str, Any], assessment: dict[str, Any] | None) -> str:
    planned = str(claim.get("active_claim") or claim.get("planned_claim") or "the planned claim").strip()
    diagnosis = str((assessment or {}).get("diagnosis") or "current evidence is weaker than the planned claim").strip()
    return (
        f"The current evidence supports a bounded exploratory interpretation of this planned claim: {planned}. "
        f"The manuscript must state the limitation explicitly because {diagnosis}"
    )


def _assessment_by_claim(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("claim_id")): item
        for item in report.get("claim_assessments") or []
        if isinstance(item, dict) and item.get("claim_id")
    }


def apply_result_downgrade(project: str | Path, *, reason: str = "") -> dict[str, Any]:
    """Choose the downgrade route: keep evidence fixed and lower manuscript claims."""
    state = load_project(project)
    project_path = state.path
    report = _read_json(project_path / "results" / "result_support_checkpoint.json", {})
    if not isinstance(report, dict) or not report:
        raise ClaimContractError("Run assess-result-support before apply-result-downgrade.")
    if report.get("decision") == "pass" and not report.get("requires_user_decision"):
        raise ClaimContractError("Result support already passes; no downgrade route is required.")
    contract_path = project_path / CLAIM_CONTRACT_JSON
    contract = _read_json(contract_path, {})
    if not isinstance(contract, dict) or not contract.get("claims"):
        raise ClaimContractError("research_plan/claim_contract.json is required before apply-result-downgrade.")
    assessments = _assessment_by_claim(report)
    changed_claims: list[dict[str, Any]] = []
    for claim in contract.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        assessment = assessments.get(str(claim.get("claim_id") or ""))
        if assessment and assessment.get("support_status") in {"not_supported", "partially_supported"}:
            previous = dict(claim)
            claim["pre_downgrade_claim"] = previous.get("active_claim") or previous.get("planned_claim")
            claim["active_claim"] = _downgrade_text(claim, assessment)
            claim["active_strength"] = "exploratory"
            claim["claim_boundary"] = "Downgraded to fit current verified result evidence; do not imply improvement, causality, robustness, or generality beyond the frozen figures and metrics."
            claim["status"] = "downgraded_to_current_evidence"
            claim["downgrade_reason"] = assessment.get("diagnosis") or reason or "Result support checkpoint required claim downgrade."
            changed_claims.append({
                "claim_id": claim.get("claim_id"),
                "previous_active_claim": previous.get("active_claim") or previous.get("planned_claim"),
                "new_active_claim": claim.get("active_claim"),
                "diagnosis": assessment.get("diagnosis"),
            })
    if not changed_claims:
        raise ClaimContractError("No failed or partial claim was available to downgrade.")
    contract["route_state"] = "downgraded_to_current_results"
    contract["last_route_decision_at"] = utc_now()
    contract["schema_version"] = "v0.18.4"
    _write_json(contract_path, contract)
    freeze = _freeze_result_artifacts(project_path, route="downgrade_research_claim")
    decision = {
        "status": "applied",
        "schema_version": "v0.18.4",
        "route": "downgrade_research_claim",
        "applied_at": utc_now(),
        "reason": reason,
        "changed_claims": changed_claims,
        "result_evidence_freeze": RESULT_EVIDENCE_FREEZE_JSON,
        "versioned_result_evidence_freeze": freeze.get("versioned_snapshot"),
        "frozen_artifact_count": freeze.get("artifact_count", 0),
        "stale_policy": "Only manuscript and claim-boundary consumers are stale; data, methods, result validity, and figures remain current.",
    }
    _write_json(project_path / CLAIM_DOWNGRADE_DECISION_JSON, decision)
    report["decision"] = "pass"
    report["support_level"] = "downgraded_supported"
    report["requires_user_decision"] = False
    report["selected_route"] = "downgrade_research_claim"
    report["manuscript_may_proceed"] = True
    report["claim_contract"] = CLAIM_CONTRACT_JSON
    report["result_evidence_freeze"] = RESULT_EVIDENCE_FREEZE_JSON
    _write_json(project_path / "results" / "result_support_checkpoint.json", report)
    markdown = _render_downgrade_markdown(decision, changed_claims)
    (project_path / "results" / "result_support_checkpoint.md").write_text(markdown, encoding="utf-8")
    write_html_report(project_path / "results" / "result_support_checkpoint.html", markdown, title="Result Support Checkpoint")
    stale = mark_stages_stale(project_path, DOWNGRADE_STALE_STAGES)
    update_stage_status(project_path, "result_support", "approved")
    return {
        "status": "applied",
        "project_path": str(project_path),
        "route": "downgrade_research_claim",
        "changed_claim_count": len(changed_claims),
        "stale_stages": stale,
        "claim_contract": str(contract_path),
        "result_evidence_freeze": str(project_path / RESULT_EVIDENCE_FREEZE_JSON),
    }


def _render_downgrade_markdown(decision: dict[str, Any], changed_claims: list[dict[str, Any]]) -> str:
    lines = [
        "# Result Support Checkpoint",
        "",
        "Decision: pass",
        "Support level: downgraded_supported",
        "Selected route: downgrade_research_claim",
        "",
        "The current figures and metrics are frozen. Draftpaper-loop will not rerun results for this route; manuscript writing must follow the downgraded active claims in `research_plan/claim_contract.json`.",
        "",
        "## Downgraded Claims",
        "",
    ]
    for item in changed_claims:
        lines.append(f"- {item.get('claim_id')}")
        lines.append(f"  - Previous: {item.get('previous_active_claim')}")
        lines.append(f"  - Active: {item.get('new_active_claim')}")
        if item.get("diagnosis"):
            lines.append(f"  - Diagnosis: {item.get('diagnosis')}")
    lines.extend(["", f"Decision file: `{CLAIM_DOWNGRADE_DECISION_JSON}`", f"Frozen evidence: `{RESULT_EVIDENCE_FREEZE_JSON}`", ""])
    return "\n".join(lines)


__all__ = [
    "CLAIM_CONTRACT_JSON",
    "CLAIM_DOWNGRADE_DECISION_JSON",
    "RESULT_EVIDENCE_FREEZE_JSON",
    "ClaimContractError",
    "build_claim_contract_from_blueprint",
    "apply_result_downgrade",
]
