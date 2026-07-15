"""Research-blueprint figure utility, caption, and confirmed-plan alignment."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .research_plan_confirmation import confirmation_state, require_confirmed_research_blueprint


ALIGNMENT_JSON = "results/confirmed_figure_alignment_report.json"
ALIGNMENT_HTML = "results/confirmed_figure_alignment_report.html"
CAPTION_JSON = "results/figure_caption_validation_report.json"
CAPTION_HTML = "results/figure_caption_validation_report.html"


class ConfirmedFigureContractError(RuntimeError):
    """Raised when a planned or generated figure diverges from the confirmed blueprint."""


_PANEL_EXPECTED_CONTENT = {
    "cohort_flow_audit": "Quantify the source, image-available, image-valid, and analysis cohorts together with every exclusion step.",
    "missingness_analysis": "Compare image missingness rates and recorded reasons across the declared sample groups and relevant covariates.",
    "representation_projection": "Visualize the representation geometry as exploratory evidence while coloring points only by the independent scientific target.",
    "target_confounder_diagnostic": "Quantify target association separately from redshift, luminosity, acquisition group, and other declared confounders.",
    "group_aware_validation": "Report held-out performance across the declared groups and folds without allowing group leakage between training and evaluation.",
    "transparent_baseline_comparison": "Compare the representation-based model with transparent catalog-only and simple predictive baselines on identical cohorts and splits.",
    "uncertainty_estimation": "Show fold- or group-level uncertainty intervals for every primary performance estimate.",
    "feature_group_ablation": "Measure the change in held-out performance when each declared feature group is removed or added on matched folds.",
    "confounder_control": "Compare image-representation gain before and after controlling the declared catalog and acquisition confounders.",
    "label_leakage_check": "Demonstrate that identifiers and label-defining variables cannot leak into the predictive feature set.",
    "confusion_or_error_analysis": "Show class-wise confusion and error patterns using held-out predictions only.",
    "class_imbalance_analysis": "Report class support together with class-wise precision, recall, and performance sensitivity to imbalance handling.",
    "uncertainty_summary": "Compare confidence or calibration evidence across classes and identify unreliable prediction regimes.",
    "anomaly_stability_analysis": "Measure candidate-rank stability across seeds, resampling, preprocessing choices, and reference cohorts.",
    "image_quality_review": "Display candidate cutouts with image-quality diagnostics to separate scientific structure from artefacts.",
    "candidate_interpretation_boundary": "Retain only stable candidates not explained by quality failures and mark them as requiring independent confirmation.",
}


def _headline(title: str) -> str:
    phrase = re.sub(r"\s+", " ", str(title or "planned scientific evidence")).strip().rstrip(".?!")
    phrase = phrase.replace(",", "").replace(";", "")
    return f"This figure establishes {phrase.lower()}."


def enrich_storyboard_figure(item: dict[str, Any], *, index: int, claim_id: str) -> dict[str, Any]:
    enriched = dict(item)
    methods = [str(value) for value in enriched.get("required_method") or ["verified_analysis"]]
    panels = enriched.get("panels") or enriched.get("panel_contract") or []
    if not panels:
        panels = [
            {
                "panel_id": f"{enriched.get('figure_id') or f'fig_{index}'}_panel_{offset}",
                "label": chr(96 + offset),
                "scientific_role": method.replace("_", " "),
                "required_method": method,
                "required_data_roles": list(enriched.get("required_data") or []),
                "expected_content": _PANEL_EXPECTED_CONTENT.get(
                    method,
                    f"Show the evidence produced by {method.replace('_', ' ')} for the contracted research question.",
                ),
            }
            for offset, method in enumerate(methods[:4], start=1)
        ]
    normalized_panels = []
    for offset, panel in enumerate(panels, start=1):
        value = dict(panel) if isinstance(panel, dict) else {"scientific_role": str(panel)}
        value.setdefault("panel_id", f"{enriched.get('figure_id') or f'fig_{index}'}_panel_{offset}")
        value.setdefault("label", chr(96 + offset))
        value.setdefault("required_data_roles", list(enriched.get("required_data") or []))
        value.setdefault("required_method", methods[min(offset - 1, len(methods) - 1)])
        value.setdefault("expected_content", f"Present the contracted {value.get('scientific_role') or 'scientific'} evidence.")
        normalized_panels.append(value)
    title = str(enriched.get("proposed_title") or enriched.get("title") or f"Scientific figure {index}")
    enriched.update({
        "claim_id": str(enriched.get("claim_id") or claim_id),
        "unique_evidence_contribution": str(enriched.get("unique_evidence_contribution") or enriched.get("expected_finding") or enriched.get("research_question") or ""),
        "why_not_table": str(enriched.get("why_not_table") or "The contracted visual comparison exposes structure, heterogeneity, or uncertainty that a scalar table alone cannot communicate."),
        "panels": normalized_panels,
        "panel_contract": normalized_panels,
        "statistical_validation_ids": list(enriched.get("statistical_validation_ids") or []),
        "caption_contract": {
            "headline": _headline(title),
            "headline_policy": "one_complete_group_level_sentence_without_comma_fragments",
            "panels": [
                {"label": panel["label"], "description": panel["expected_content"], "panel_id": panel["panel_id"]}
                for panel in normalized_panels
            ],
            "statistics": "Define the cohort, sample unit, estimand, uncertainty, and any threshold used by the displayed evidence.",
            "claim_boundary": str(enriched.get("scientific_claim_boundary") or "Interpret only within the confirmed data, method, and validation boundary."),
        },
    })
    return enriched


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _canonical_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value] if value else []
    return sorted({re.sub(r"\s+", "_", str(item).strip().lower()) for item in values if str(item).strip()})


def _canonical_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def attach_confirmed_contract_to_plan(project: str | Path, figures: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    state = confirmation_state(project)
    if not state.get("required"):
        return figures, None
    snapshot = require_confirmed_research_blueprint(project)
    plan_hash = str(snapshot.get("confirmed_plan_hash") or "")
    confirmed_storyboard = ((snapshot.get("embedded_contracts") or {}).get("research_plan/figure_storyboard.json") or {})
    by_id = {
        str(item.get("figure_id") or item.get("id") or ""): item
        for item in confirmed_storyboard.get("figures") or []
        if isinstance(item, dict)
    }
    attached = []
    for figure in figures:
        item = dict(figure)
        storyboard_id = str(item.get("storyboard_id") or item.get("id") or "")
        contract = by_id.get(storyboard_id)
        if item.get("figure_role") == "main_result" and not contract:
            raise ConfirmedFigureContractError(f"Main figure {storyboard_id} is absent from the confirmed storyboard.")
        if contract:
            item.update({
                "confirmed_plan_hash": plan_hash,
                "claim_id": contract.get("claim_id"),
                "research_question": contract.get("research_question"),
                "scientific_question": contract.get("research_question"),
                "expected_finding": contract.get("expected_finding"),
                "unique_evidence_contribution": contract.get("unique_evidence_contribution"),
                "why_not_table": contract.get("why_not_table"),
                "required_data": list(contract.get("required_data") or []),
                "required_method": list(contract.get("required_method") or []),
                "panel_contract": contract.get("panel_contract") or contract.get("panels") or [],
                "data_requirement_ids": [f"data:{storyboard_id}:{value}" for value in contract.get("required_data") or []],
                "method_requirement_ids": [f"method:{storyboard_id}:{value}" for value in contract.get("required_method") or []],
                "statistical_validation_ids": contract.get("statistical_validation_ids") or [],
                "caption_contract": contract.get("caption_contract") or {},
                "caption_draft": ((contract.get("caption_contract") or {}).get("headline") or item.get("caption_draft")),
            })
        attached.append(item)
    return attached, plan_hash


def _alignment_issues(confirmed: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    issues = []
    pairs = [
        ("claim_id", [confirmed.get("claim_id")], [observed.get("claim_id")]),
        ("required_data", confirmed.get("required_data"), observed.get("required_data")),
        ("required_method", confirmed.get("required_method"), observed.get("required_method")),
        ("statistical_validation_ids", confirmed.get("statistical_validation_ids"), observed.get("statistical_validation_ids")),
    ]
    for name, expected, actual in pairs:
        if _canonical_list(expected) != _canonical_list(actual):
            issues.append(f"{name} differs from confirmed contract")
    for name in ("research_question", "expected_finding", "unique_evidence_contribution", "why_not_table"):
        if _canonical_text(confirmed.get(name)) != _canonical_text(observed.get(name)):
            issues.append(f"{name} differs from confirmed contract")
    expected_panels = [item for item in confirmed.get("panel_contract") or confirmed.get("panels") or [] if isinstance(item, dict)]
    actual_panels = [item for item in observed.get("panel_contract") or observed.get("panels") or [] if isinstance(item, dict)]
    expected_panel_ids = [str(item.get("panel_id")) for item in expected_panels]
    actual_panel_ids = [str(item.get("panel_id")) for item in actual_panels]
    if expected_panel_ids != actual_panel_ids:
        issues.append("panel structure differs from confirmed contract")
    else:
        for expected, actual in zip(expected_panels, actual_panels):
            panel_id = str(expected.get("panel_id") or "unknown_panel")
            for name in ("label", "scientific_role", "expected_content"):
                if _canonical_text(expected.get(name)) != _canonical_text(actual.get(name)):
                    issues.append(f"panel {panel_id} {name} differs from confirmed contract")
            if _canonical_list(expected.get("required_data_roles")) != _canonical_list(actual.get("required_data_roles")):
                issues.append(f"panel {panel_id} required_data_roles differ from confirmed contract")
            if _canonical_list(expected.get("required_method")) != _canonical_list(actual.get("required_method")):
                issues.append(f"panel {panel_id} required_method differs from confirmed contract")
    return issues


def _render_alignment(report: dict[str, Any]) -> str:
    lines = ["# Confirmed Figure Alignment", "", f"Decision: `{report['decision']}`", ""]
    for item in report.get("figure_checks") or []:
        lines.append(f"- `{item['figure_id']}`: {item['decision']} ({'; '.join(item['issues']) or 'aligned'})")
    return "\n".join(lines)


def validate_confirmed_figure_alignment(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    snapshot = require_confirmed_research_blueprint(state.path)
    if not snapshot:
        report = {"schema_version": "dpl.confirmed_figure_alignment.v1", "status": "not_required", "decision": "pass", "figure_checks": []}
        _write_json(state.path / ALIGNMENT_JSON, report)
        return report
    confirmed_storyboard = ((snapshot.get("embedded_contracts") or {}).get("research_plan/figure_storyboard.json") or {})
    observed_plan = _read_json(state.path / "results" / "figure_plan.json")
    confirmed_by_id = {str(item.get("figure_id") or item.get("id") or ""): item for item in confirmed_storyboard.get("figures") or [] if isinstance(item, dict)}
    observed_by_id = {str(item.get("storyboard_id") or item.get("id") or ""): item for item in observed_plan.get("figures") or [] if isinstance(item, dict) and item.get("figure_role") == "main_result"}
    checks = []
    for figure_id, contract in confirmed_by_id.items():
        observed = observed_by_id.get(figure_id)
        issues = ["confirmed figure missing from executable plan"] if not observed else _alignment_issues(contract, observed)
        if observed and observed.get("confirmed_plan_hash") != snapshot.get("confirmed_plan_hash"):
            issues.append("confirmed plan hash missing or mismatched")
        checks.append({"figure_id": figure_id, "decision": "pass" if not issues else "blocked", "issues": issues})
    extras = sorted(set(observed_by_id) - set(confirmed_by_id))
    for figure_id in extras:
        checks.append({"figure_id": figure_id, "decision": "blocked", "issues": ["unconfirmed extra main figure"]})
    decision = "pass" if all(item["decision"] == "pass" for item in checks) else "blocked"
    report = {
        "schema_version": "dpl.confirmed_figure_alignment.v1",
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "confirmed_plan_hash": snapshot.get("confirmed_plan_hash"),
        "decision": decision,
        "figure_checks": checks,
        "policy": "No method, data role, panel, statistical design, or main figure may silently replace the human-confirmed contract.",
    }
    _write_json(state.path / ALIGNMENT_JSON, report)
    write_html_report(state.path / ALIGNMENT_HTML, _render_alignment(report), title="Confirmed Figure Alignment")
    if decision != "pass":
        raise ConfirmedFigureContractError("Executable figure plan diverges from the human-confirmed research blueprint.")
    return report


def _caption_issues(contract: dict[str, Any]) -> list[str]:
    issues = []
    headline = str(contract.get("headline") or "").strip()
    if not headline or headline[-1:] not in ".!?。！？":
        issues.append("headline is not a complete sentence")
    if "," in headline or ";" in headline or "，" in headline or "；" in headline:
        issues.append("headline contains comma- or semicolon-linked fragments")
    if re.match(r"^\s*(?:\([a-zA-Z]\)|[a-zA-Z][.)])\s*", headline):
        issues.append("headline starts with a panel label")
    panels = [item for item in contract.get("panels") or [] if isinstance(item, dict)]
    if not panels or any(not item.get("label") or not item.get("description") for item in panels):
        issues.append("one or more panels lack ordered descriptions")
    if not str(contract.get("statistics") or "").strip():
        issues.append("statistics or uncertainty definition is missing")
    if not str(contract.get("claim_boundary") or "").strip():
        issues.append("claim boundary is missing")
    return issues


def validate_figure_captions(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    plan = _read_json(state.path / "results" / "figure_plan.json")
    checks = []
    for figure in plan.get("figures") or []:
        if not isinstance(figure, dict) or figure.get("figure_role") != "main_result":
            continue
        contract = figure.get("caption_contract") if isinstance(figure.get("caption_contract"), dict) else {}
        issues = _caption_issues(contract)
        checks.append({"figure_id": figure.get("id"), "decision": "pass" if not issues else "repair_required", "issues": issues})
    decision = "pass" if checks and all(item["decision"] == "pass" for item in checks) else "repair_required"
    report = {"schema_version": "dpl.figure_caption_validation.v1", "status": "written", "generated_at": utc_now(), "decision": decision, "figure_checks": checks}
    _write_json(state.path / CAPTION_JSON, report)
    write_html_report(state.path / CAPTION_HTML, _render_alignment(report), title="Figure Caption Validation")
    return report
