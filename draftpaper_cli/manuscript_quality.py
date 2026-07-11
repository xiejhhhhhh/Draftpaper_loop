# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Contract-based manuscript quality assessment without reference-prose copying."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


NARRATIVE_CONTRACT = "results/results_narrative_contract.json"
QUALITY_REPORT = "review/results_manuscript_quality.json"
QUALITY_THRESHOLD = 0.95


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _narrative_role(figure: dict[str, Any]) -> str:
    title = " ".join(str(figure.get(key) or "") for key in ["title", "caption_draft"]).lower()
    question = " ".join(str(figure.get(key) or "") for key in ["scientific_question", "research_question"]).lower()
    blob = " ".join([title, question, str(figure.get("result_claim") or ""), str(figure.get("expected_finding") or "")]).lower()
    if any(term in title for term in ["ablation", "component contribution"]):
        return "component_attribution"
    if any(term in title for term in ["uncertainty", "error", "confusion", "misclass", "calibration"]):
        return "error_uncertainty"
    if any(term in title for term in ["baseline", "versus", "model performance", "comparison"]):
        return "model_comparison"
    if any(term in title for term in ["before training", "feature space", "separab", "pre-model", "premodel"]):
        return "premodel_signal"
    if any(term in title for term in ["coverage", "sample", "cohort", "modality", "workflow", "study boundary"]):
        return "study_boundary"
    if any(term in question for term in ["outperform", "baseline", "model performance"]):
        return "model_comparison"
    if any(term in question for term in ["uncertain", "error", "misclass"]):
        return "error_uncertainty"
    if any(term in blob for term in ["ablation", "component", "remove", "contribution"]):
        return "component_attribution"
    return "empirical_finding"


def _metrics(run_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for name, value in (run_manifest.get("metrics") or {}).items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        result.append({"metric_name": str(name), "value": numeric, "run_id": run_manifest.get("run_id") or ""})
    return result


def _metrics_for_role(metrics: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    terms = {
        "study_boundary": {"count", "sample", "source", "event", "coverage", "imbalance"},
        "premodel_signal": {"pearson", "r2", "separation", "silhouette", "pca"},
        "model_comparison": {"baseline", "proposed", "model", "transformer", "f1", "auc", "accuracy"},
        "component_attribution": {"ablation", "without", "remove", "delta", "component"},
        "error_uncertainty": {"error", "confusion", "uncertainty", "calibration", "brier"},
    }.get(role, set())
    selected = [item for item in metrics if any(term in _normalise(item["metric_name"]) for term in terms)]
    return selected


def build_results_narrative_contract(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contracts_payload = _read_json(state.path / "results" / "figure_contracts.json")
    contracts = contracts_payload.get("main_contracts") or contracts_payload.get("contracts") or []
    manifest = _read_json(state.path / "results" / "result_manifest.yaml")
    manifest_figures = manifest.get("main_figures") or manifest.get("figures") or []
    manifest_by_id = {
        str(item.get("figure_id") or item.get("storyboard_id") or item.get("id") or ""): item
        for item in manifest_figures if isinstance(item, dict)
    }
    verified_metrics = _metrics(_read_json(state.path / "methods" / "run_manifest.yaml"))
    groups = []
    for index, raw in enumerate(contracts, start=1):
        if not isinstance(raw, dict) or str(raw.get("manuscript_role") or "main").lower() == "appendix":
            continue
        figure_id = str(raw.get("figure_id") or raw.get("storyboard_id") or raw.get("id") or f"figure_{index:02d}")
        figure = {**manifest_by_id.get(figure_id, {}), **raw}
        role = _narrative_role(figure)
        groups.append({
            "figure_id": figure_id,
            "narrative_role": role,
            "scientific_question": str(figure.get("scientific_question") or figure.get("research_question") or ""),
            "expected_finding": str(figure.get("result_claim") or figure.get("expected_finding") or ""),
            "claim_boundary": str(figure.get("claim_boundary") or ""),
            "verified_metrics": _metrics_for_role(verified_metrics, role),
            "required_reasoning": {
                "study_boundary": ["cohort_or_sample_boundary", "available_modalities"],
                "premodel_signal": ["observed_structure", "non_causal_boundary"],
                "model_comparison": ["baseline_direction", "validation_context"],
                "component_attribution": ["ablation_direction", "component_interpretation"],
                "error_uncertainty": ["error_pattern", "uncertainty_or_follow_up_boundary"],
            }.get(role, ["empirical_pattern", "claim_boundary"]),
        })
    payload = {
        "status": "written",
        "schema_version": "v0.21.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "minimum_quality_score": QUALITY_THRESHOLD,
        "figure_groups": groups,
        "verified_metrics": verified_metrics,
        "policy": "Codex composes freely, but every main evidence role must be interpreted with run-bound facts and calibrated claim boundaries.",
    }
    _write_json(state.path / NARRATIVE_CONTRACT, payload)
    return payload


def _metric_claims(text: str) -> list[tuple[str, float]]:
    pattern = re.compile(r"((?:macro\s+)?(?:f1|auc|accuracy|r2|r\^2|rmse|mae))\s*(?:of|=|was|is|reached|to)?\s*([0-9]+(?:\.[0-9]+)?)", re.I)
    return [(_normalise(match.group(1)).replace("macro_", ""), float(match.group(2))) for match in pattern.finditer(text)]


def _verified_metric_pairs(contract: dict[str, Any]) -> list[tuple[str, float]]:
    pairs = []
    for item in contract.get("verified_metrics") or []:
        name = _normalise(item.get("metric_name"))
        canonical = "f1" if "f1" in name else "auc" if "auc" in name else "accuracy" if "accuracy" in name else name
        pairs.append((canonical, float(item.get("value"))))
    return pairs


def assess_results_manuscript_quality(
    project: str | Path,
    *,
    text: str | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    contract = contract or _read_json(state.path / NARRATIVE_CONTRACT) or build_results_narrative_contract(state.path)
    if text is None:
        text = (state.path / "results" / "results.tex").read_text(encoding="utf-8-sig", errors="replace")
    lowered = text.lower()
    issues: list[dict[str, Any]] = []

    verified = _verified_metric_pairs(contract)
    untraceable = [
        (name, value) for name, value in _metric_claims(text)
        if not any(name == known_name and abs(value - known_value) <= 0.0002 for known_name, known_value in verified)
    ]
    for name, value in untraceable:
        issues.append({"kind": "untraceable_metric_claim", "metric_name": name, "value": value})
    evidence_fidelity = 1.0 if not untraceable else max(0.0, 1.0 - 0.5 * len(untraceable))

    role_markers = {
        "study_boundary": ["boundary", "cohort", "sample", "modalit"],
        "premodel_signal": ["pre-model", "before model", "separation", "threshold"],
        "model_comparison": ["baseline", "whereas", "outperform", "strongest"],
        "component_attribution": ["ablation", "removed", "removing", "contribut"],
        "error_uncertainty": ["error", "uncertainty", "intermediate", "confusion"],
        "empirical_finding": ["figure", "evidence", "result"],
    }
    required_roles = {str(item.get("narrative_role")) for item in contract.get("figure_groups") or []}
    covered_roles = {
        role for role in required_roles
        if any(marker in lowered for marker in role_markers.get(role, []))
    }
    missing_roles = sorted(required_roles - covered_roles)
    if missing_roles:
        issues.append({"kind": "missing_narrative_roles", "roles": missing_roles})
    narrative_coverage = len(covered_roles) / max(1, len(required_roles))

    reasoning_checks = [
        not ({"model_comparison"} & required_roles) or ("baseline" in lowered and any(term in lowered for term in ["whereas", "outperform", "stronger", "remains"])),
        not ({"component_attribution"} & required_roles) or ("ablation" in lowered and any(term in lowered for term in ["remov", "contribut", "component"])),
        not ({"error_uncertainty"} & required_roles) or ("error" in lowered and "uncertainty" in lowered),
        not ({"premodel_signal"} & required_roles) or any(term in lowered for term in ["not a simple threshold", "not establish", "partial", "overlap"]),
    ]
    scientific_reasoning = sum(reasoning_checks) / len(reasoning_checks)

    calibration_markers = ["current cohort", "validation", "does not", "rather than", "limit", "boundary"]
    claim_calibration = min(1.0, sum(marker in lowered for marker in calibration_markers) / 3.0)

    sentences = [re.sub(r"\s+", " ", item).strip().lower() for item in re.split(r"(?<=[.!?])\s+", text) if len(item.split()) >= 8]
    duplicate_count = len(sentences) - len(set(sentences))
    generic_count = sum(text.count(marker) for marker in [
        "The interpretation remains limited to the verified data, method design, and validation setting.",
        "first establishes the main empirical pattern while the second checks",
    ])
    if duplicate_count or generic_count:
        issues.append({"kind": "repetitive_template_prose", "duplicate_sentence_count": duplicate_count, "generic_phrase_count": generic_count})
    prose_quality = max(0.0, 1.0 - 0.25 * duplicate_count - 0.2 * generic_count)

    dimensions = {
        "evidence_fidelity": evidence_fidelity,
        "narrative_coverage": narrative_coverage,
        "scientific_reasoning": scientific_reasoning,
        "claim_calibration": claim_calibration,
        "prose_quality": prose_quality,
    }
    weights = {"evidence_fidelity": 0.30, "narrative_coverage": 0.25, "scientific_reasoning": 0.20, "claim_calibration": 0.15, "prose_quality": 0.10}
    score = round(sum(dimensions[key] * weights[key] for key in weights), 4)
    report = {
        "status": "written",
        "schema_version": "v0.21.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": score,
        "minimum_score": QUALITY_THRESHOLD,
        "decision": "pass" if score >= QUALITY_THRESHOLD and not untraceable else "repair_required",
        "dimensions": dimensions,
        "issues": issues,
        "contract": NARRATIVE_CONTRACT,
    }
    _write_json(state.path / QUALITY_REPORT, report)
    return report
