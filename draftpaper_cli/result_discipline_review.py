# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Post-Results composite-discipline review-rule audit."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project
from .review_rule_runtime import assess_review_rules
from .manuscript_quality import assess_results_manuscript_quality, build_results_narrative_contract
from .scientific_figure_quality import assess_scientific_figure_quality


REPORT_JSON = "review/result_discipline_review_report.json"
REPORT_HTML = "review/result_discipline_review_report.html"


class ResultDisciplineReviewError(RuntimeError):
    """Raised when Results cannot be audited against discipline evidence."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_or_empty(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _render(report: dict[str, Any]) -> str:
    lines = ["# Results Discipline Review", "", f"Decision: `{report.get('decision')}`", "", "## Next Action", ""]
    action = report.get("recommended_next_action") or {}
    lines.append(f"`{action.get('command')}` -- {action.get('reason')}")
    lines.extend(["", "## Rule Assessments", ""])
    for item in (report.get("review_rule_gate") or {}).get("rule_assessments") or []:
        lines.append(f"- `{item.get('rule_id')}`: {item.get('decision')} ({item.get('runtime_level')})")
    return "\n".join(lines)


def _canonical_metric_name(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    aliases = {"macro_f1": "f1", "f1_macro": "f1", "roc_auc": "auc", "roc_auc_xrb": "auc", "r_2": "r2"}
    if normalized in aliases:
        return aliases[normalized]
    if "f1" in normalized:
        return "f1"
    if "auc" in normalized:
        return "auc"
    return normalized


def _numeric_metrics(project_path: Path) -> list[dict[str, Any]]:
    manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    values: list[dict[str, Any]] = []
    for name, value in (manifest.get("metrics") or {}).items():
        try:
            values.append({"metric_name": _canonical_metric_name(name), "value": float(value), "run_id": manifest.get("run_id")})
        except (TypeError, ValueError):
            continue
    evidence = _read_json(project_path / "results" / "resolved_result_evidence.json")
    if not evidence:
        evidence = _read_json(project_path / "results" / "result_evidence_resolution.json")
    for item in evidence.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        try:
            values.append({
                "metric_name": _canonical_metric_name(item.get("metric_name") or item.get("name")),
                "value": float(item.get("value")),
                "run_id": item.get("run_id") or evidence.get("run_id"),
                "cohort": item.get("cohort") or item.get("split"),
            })
        except (TypeError, ValueError):
            continue
    return values


def _audit_results_semantics(project_path: Path, text: str) -> dict[str, Any]:
    issues = []
    prose = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", "", text, flags=re.DOTALL)
    internal_pattern = re.compile(r"(?:[A-Za-z]:\\|(?:results|data|methods|code)/[^\s{}]+\.(?:csv|tsv|json|py|png))", re.IGNORECASE)
    for match in internal_pattern.finditer(prose):
        issues.append({"kind": "internal_artifact_language", "severity": "repair_required", "detail": match.group(0)})
    if "\\cite" in prose:
        issues.append({"kind": "results_citation_present", "severity": "repair_required", "detail": "Results must not use literature citations as a substitute for result evidence."})
    metric_values = _numeric_metrics(project_path)
    metric_pattern = re.compile(r"((?:macro\s+)?(?:f1|auc|accuracy|r2|r\^2|rmse|mae))\s*(?:of|=|was|is|reached)?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
    for match in metric_pattern.finditer(prose):
        metric_name = _canonical_metric_name(match.group(1))
        value = float(match.group(2))
        if not any(item.get("metric_name") == metric_name and abs(value - float(item.get("value"))) <= 0.0002 for item in metric_values):
            issues.append({"kind": "untraceable_metric_claim", "severity": "repair_required", "detail": f"{match.group(0).strip()} is not present in verified result evidence."})
    if not re.search(r"(?:Figure|Fig\.)\s*~?\\?ref\{|Figure\s+\d", prose, flags=re.IGNORECASE):
        issues.append({"kind": "missing_figure_interpretation", "severity": "warning", "detail": "Results prose does not explicitly interpret a figure reference."})
    return {"status": "written", "verified_metric_values": metric_values, "issues": issues}


def review_results_with_discipline_rules(project: str | Path) -> dict[str, Any]:
    """Audit final Results against the complete figure trace and composite rules.

    Rules are selected only for figures with actual data/method plugin traces.
    Findings drive Results repair; they do not retroactively prevent figure
    generation. Final figure impossibility is owned by capability rescue.
    """
    state = load_project(project)
    results_path = state.path / "results" / "results.tex"
    if not results_path.exists():
        raise ResultDisciplineReviewError("results/results.tex is required before post-Results discipline review.")
    trace = _read_json(state.path / "results" / "figure_plugin_trace_report.json")
    if not trace:
        from .figure_plugin_trace import validate_figure_plugin_trace

        trace = validate_figure_plugin_trace(state.path)
    figure_checks = [item for item in trace.get("figure_checks") or [] if isinstance(item, dict)]
    reviewable = [
        item for item in figure_checks
        if item.get("data_plugin_ids") and item.get("method_plugin_ids") and item.get("run_output_event_id")
    ]
    reviewed_figure_ids = [str(item.get("figure_id")) for item in reviewable if item.get("figure_id")]
    skipped_figure_ids = [
        str(item.get("figure_id")) for item in figure_checks
        if item.get("figure_id") and item not in reviewable
    ]
    active_plugin_ids = sorted({
        str(plugin_id)
        for item in reviewable
        for plugin_id in [*(item.get("data_plugin_ids") or []), *(item.get("method_plugin_ids") or [])]
        if plugin_id
    })
    results_bytes = results_path.read_bytes()
    results_semantic_audit = _audit_results_semantics(state.path, results_bytes.decode("utf-8-sig", errors="replace"))
    narrative_contract = build_results_narrative_contract(state.path)
    manuscript_quality = (
        assess_results_manuscript_quality(
            state.path,
            text=results_bytes.decode("utf-8-sig", errors="replace"),
            contract=narrative_contract,
        )
        if len(narrative_contract.get("figure_groups") or []) >= 3
        else {"decision": "not_assessed", "score": None, "issues": []}
    )
    figure_quality = (
        assess_scientific_figure_quality(state.path)
        if len(narrative_contract.get("figure_groups") or []) >= 3
        else {"decision": "not_assessed", "score": None, "issues": []}
    )
    evidence_context = {
        "available_evidence_roles": ["results_prose", "figure_plugin_trace", "plugin_binding_plan", "run_id"],
        "figure_plugin_trace_decision": trace.get("decision"),
        "active_plugin_ids": active_plugin_ids,
        "reviewed_figure_ids": reviewed_figure_ids,
        "results_semantic_issues": results_semantic_audit["issues"],
    }
    if reviewable:
        rule_gate = assess_review_rules(
            state.path,
            stage="post_results",
            evidence_context=evidence_context,
            write_path=state.path / "review" / "result_discipline_review_rule_gate.json",
        )
    else:
        rule_gate = {
            "decision": "pass",
            "selected_rule_count": 0,
            "rule_assessments": [],
            "rescue_tasks": [],
            "recommended_next_commands": [],
            "policy": "No data/method-plugin-generated figure was present, so discipline plugin review rules were not activated.",
        }
    semantic_repairs = [item for item in results_semantic_audit["issues"] if item.get("severity") == "repair_required"]
    if semantic_repairs or manuscript_quality.get("decision") == "repair_required" or figure_quality.get("decision") == "repair_required":
        decision = "repair_required"
        action = {
            "command": "verify-methods" if figure_quality.get("decision") == "repair_required" else "prepare-results-semantic-repair",
            "reason": "Figures or Results require repair before they meet the 0.95 publication-quality contracts.",
        }
    elif rule_gate.get("decision") == "revise_required":
        decision = "repair_required"
        rescue = (rule_gate.get("rescue_tasks") or [{}])[0]
        action = {
            "command": rescue.get("recommended_command") or "prepare-result-rescue",
            "reason": rescue.get("reason") or "A promoted discipline review rule requires evidence repair.",
        }
    else:
        decision = "pass"
        action = {"command": "write-introduction", "reason": "Results and composite discipline review are ready for downstream manuscript writing."}
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "results_sha256": hashlib.sha256(results_bytes).hexdigest(),
        "evidence_snapshot_id": _read_json(state.path / "core_evidence" / "core_evidence_report.json").get("promoted_evidence_snapshot_id") or "",
        "result_manifest_sha256": _sha256_or_empty(state.path / "results" / "result_manifest.yaml"),
        "figure_plugin_trace_sha256": _sha256_or_empty(state.path / "results" / "figure_plugin_trace_report.json"),
        "trace_decision": trace.get("decision"),
        "reviewed_figure_ids": reviewed_figure_ids,
        "skipped_figure_ids": skipped_figure_ids,
        "active_plugin_ids": active_plugin_ids,
        "figure_plugin_trace": "results/figure_plugin_trace_report.json",
        "review_rule_gate": rule_gate,
        "results_semantic_audit": results_semantic_audit,
        "manuscript_quality": manuscript_quality,
        "figure_publication_quality": figure_quality,
        "recommended_next_action": action,
        "policy": "Only plugin-generated figures activate discipline review rules. Findings repair Results claims and scientific interpretation; they do not retroactively block figure generation. Citation audit remains later and preserves references.",
    }
    _write_json(state.path / REPORT_JSON, report)
    write_html_report(state.path / REPORT_HTML, _render(report), title="Results Discipline Review")
    return {"status": "written", "project_path": str(state.path), "decision": decision, "report": REPORT_JSON, "recommended_next_action": action["command"]}
