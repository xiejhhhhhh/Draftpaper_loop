"""Single public façade for figure-contract issue normalization and assessment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .figure_contract_gate import FigureContractGateError, assess_figure_contracts
from .figure_contracts_v026 import (
    ALIGNMENT_JSON,
    CAPTION_JSON,
    ConfirmedFigureContractError,
    validate_confirmed_figure_alignment,
    validate_figure_captions,
)
from .io_utils import read_json_object, write_json


FIGURE_CONTRACT_ASSESSMENT_JSON = "results/figure_contract_assessment.json"


def _append_issue(
    issues: list[dict[str, str]],
    seen: set[tuple[str, str, str, str]],
    *,
    source: str,
    code: str,
    severity: str,
    message: str,
    figure_id: str = "",
) -> None:
    normalized = (source, code or "unspecified", figure_id, " ".join(message.split()))
    if not normalized[3] or normalized in seen:
        return
    seen.add(normalized)
    issues.append(
        {
            "source": normalized[0],
            "code": normalized[1],
            "severity": severity or "warning",
            "message": normalized[3],
            "figure_id": figure_id,
        }
    )


def _direct_issues(
    report: dict[str, Any],
    *,
    source: str,
    issues: list[dict[str, str]],
    seen: set[tuple[str, str, str, str]],
) -> None:
    for item in report.get("issues") or []:
        if isinstance(item, str):
            _append_issue(issues, seen, source=source, code="reported_issue", severity="blocking", message=item)
            continue
        if not isinstance(item, dict):
            continue
        _append_issue(
            issues,
            seen,
            source=source,
            code=str(item.get("code") or item.get("kind") or "reported_issue"),
            severity=str(item.get("severity") or "blocking"),
            message=str(item.get("message") or item.get("detail") or ""),
            figure_id=str(item.get("figure_id") or item.get("storyboard_id") or ""),
        )


def _check_issues(
    report: dict[str, Any],
    *,
    source: str,
    code: str,
    severity: str,
    issues: list[dict[str, str]],
    seen: set[tuple[str, str, str, str]],
) -> None:
    for check in report.get("figure_checks") or report.get("checks") or []:
        if not isinstance(check, dict):
            continue
        for item in check.get("issues") or []:
            _append_issue(
                issues,
                seen,
                source=source,
                code=code,
                severity=severity,
                message=str(item),
                figure_id=str(check.get("figure_id") or check.get("storyboard_id") or ""),
            )


def collect_figure_contract_issues(
    *,
    gate_report: dict[str, Any] | None = None,
    semantic_report: dict[str, Any] | None = None,
    alignment_report: dict[str, Any] | None = None,
    caption_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize all figure-contract reports into one deterministic issue list."""
    issues: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    gate = gate_report or {}
    semantics = semantic_report or {}
    alignment = alignment_report or {}
    captions = caption_report or {}
    _direct_issues(gate, source="figure_contract_gate", issues=issues, seen=seen)
    _direct_issues(semantics, source="figure_semantics", issues=issues, seen=seen)
    _check_issues(
        alignment,
        source="confirmed_alignment",
        code="confirmed_contract_mismatch",
        severity="blocking",
        issues=issues,
        seen=seen,
    )
    _check_issues(
        captions,
        source="caption_contract",
        code="caption_contract_violation",
        severity="repair_required",
        issues=issues,
        seen=seen,
    )
    decision = "blocked" if any(item["severity"] in {"blocking", "rescue_required"} for item in issues) else (
        "repair_required" if issues else "pass"
    )
    return {
        "schema_version": "dpl.figure_contract_assessment.v1",
        "status": "assessed",
        "decision": decision,
        "issue_count": len(issues),
        "issues": issues,
        "source_decisions": {
            "figure_contract_gate": gate.get("decision"),
            "figure_semantics": semantics.get("decision"),
            "confirmed_alignment": alignment.get("decision"),
            "caption_contract": captions.get("decision"),
        },
    }


def assess_project_figure_contracts(project: str | Path) -> dict[str, Any]:
    """Run project-level figure checks and persist their normalized assessment."""
    root = Path(project)
    try:
        gate = assess_figure_contracts(root, propagate_stage_state=False)
    except FigureContractGateError as exc:
        gate = {"decision": "blocked", "issues": [{"kind": "gate_error", "severity": "blocking", "detail": str(exc)}]}
    try:
        alignment = validate_confirmed_figure_alignment(root)
    except ConfirmedFigureContractError:
        alignment = read_json_object(root / ALIGNMENT_JSON)
    captions = validate_figure_captions(root)
    semantics = read_json_object(root / "results" / "figure_semantic_validation_report.json")
    report = collect_figure_contract_issues(
        gate_report=gate,
        semantic_report=semantics,
        alignment_report=alignment,
        caption_report=captions,
    )
    write_json(root / FIGURE_CONTRACT_ASSESSMENT_JSON, report)
    return report
