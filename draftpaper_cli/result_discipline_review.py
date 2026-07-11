# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Post-Results composite-discipline review-rule audit."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project
from .review_rule_runtime import assess_review_rules


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


def _render(report: dict[str, Any]) -> str:
    lines = ["# Results Discipline Review", "", f"Decision: `{report.get('decision')}`", "", "## Next Action", ""]
    action = report.get("recommended_next_action") or {}
    lines.append(f"`{action.get('command')}` -- {action.get('reason')}")
    lines.extend(["", "## Rule Assessments", ""])
    for item in (report.get("review_rule_gate") or {}).get("rule_assessments") or []:
        lines.append(f"- `{item.get('rule_id')}`: {item.get('decision')} ({item.get('runtime_level')})")
    return "\n".join(lines)


def _numeric_metrics(project_path: Path) -> list[float]:
    manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    values = []
    for value in (manifest.get("metrics") or {}).values():
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    evidence = _read_json(project_path / "results" / "result_evidence_resolution.json")
    for item in evidence.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        try:
            values.append(float(item.get("value")))
        except (TypeError, ValueError):
            continue
    return values


def _audit_results_semantics(project_path: Path, text: str) -> dict[str, Any]:
    issues = []
    prose = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", "", text, flags=re.DOTALL)
    internal_pattern = re.compile(r"(?:[A-Za-z]:\\|(?:results|data|methods|code)/[^\s{}]+\.(?:csv|tsv|json|py|png))", re.IGNORECASE)
    for match in internal_pattern.finditer(prose):
        issues.append({"kind": "internal_artifact_language", "severity": "blocking", "detail": match.group(0)})
    if "\\cite" in prose:
        issues.append({"kind": "results_citation_present", "severity": "blocking", "detail": "Results must not use literature citations as a substitute for result evidence."})
    metric_values = _numeric_metrics(project_path)
    metric_pattern = re.compile(r"(?:macro\s+)?(?:f1|auc|accuracy|r2|r\^2|rmse|mae)\s*(?:of|=|was|is|reached)?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
    for match in metric_pattern.finditer(prose):
        value = float(match.group(1))
        if metric_values and not any(abs(value - known) <= 0.0002 for known in metric_values):
            issues.append({"kind": "untraceable_metric_claim", "severity": "blocking", "detail": f"{match.group(0).strip()} is not present in verified result evidence."})
    if not re.search(r"(?:Figure|Fig\.)\s*~?\\?ref\{|Figure\s+\d", prose, flags=re.IGNORECASE):
        issues.append({"kind": "missing_figure_interpretation", "severity": "warning", "detail": "Results prose does not explicitly interpret a figure reference."})
    return {"status": "written", "verified_metric_values": metric_values, "issues": issues}


def review_results_with_discipline_rules(project: str | Path) -> dict[str, Any]:
    """Audit final Results against the complete figure trace and composite rules.

    A missing claim/plugin/run/review trace is always a workflow block. Scientific
    blocking by a review rule remains restricted to mature, evidence-bound rules
    as enforced by ``review_rule_runtime``.
    """
    state = load_project(project)
    results_path = state.path / "results" / "results.tex"
    if not results_path.exists():
        raise ResultDisciplineReviewError("results/results.tex is required before post-Results discipline review.")
    trace = _read_json(state.path / "results" / "figure_plugin_trace_report.json")
    if not trace:
        from .figure_plugin_trace import validate_figure_plugin_trace

        trace = validate_figure_plugin_trace(state.path)
    bindings = _read_json(state.path / "research_plan" / "plugin_binding_plan.json")
    results_semantic_audit = _audit_results_semantics(state.path, results_path.read_text(encoding="utf-8-sig", errors="replace"))
    evidence_context = {
        "available_evidence_roles": ["results_prose", "figure_plugin_trace", "plugin_binding_plan"],
        "figure_plugin_trace_decision": trace.get("decision"),
        "bound_review_rule_ids": [
            item.get("plugin_id") for item in bindings.get("bindings") or []
            if isinstance(item, dict) and item.get("kind") == "review"
        ],
        "results_semantic_issues": results_semantic_audit["issues"],
    }
    rule_gate = assess_review_rules(
        state.path,
        stage="assess_result_validity",
        evidence_context=evidence_context,
        write_path=state.path / "review" / "result_discipline_review_rule_gate.json",
    )
    semantic_blocking = [item for item in results_semantic_audit["issues"] if item.get("severity") == "blocking"]
    if trace.get("decision") != "pass":
        decision = "revise_required"
        action = {
            "command": "prepare-plugin-rescue" if trace.get("decision") == "blocked" else "verify-methods",
            "reason": "Results cannot be accepted until every main figure has a complete claim, plugin, verified run-output, and review-rule trace.",
        }
    elif semantic_blocking:
        decision = "revise_required"
        action = {"command": "write-results", "reason": "Results semantic audit found an untraceable metric, citation, or internal artifact expression."}
    elif rule_gate.get("decision") == "revise_required":
        decision = "revise_required"
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
        "trace_decision": trace.get("decision"),
        "figure_plugin_trace": "results/figure_plugin_trace_report.json",
        "review_rule_gate": rule_gate,
        "results_semantic_audit": results_semantic_audit,
        "recommended_next_action": action,
        "policy": "Citation audit occurs only after final manuscript sections; this review checks scientific evidence and result claims without deleting references.",
    }
    _write_json(state.path / REPORT_JSON, report)
    write_html_report(state.path / REPORT_HTML, _render(report), title="Results Discipline Review")
    return {"status": "written", "project_path": str(state.path), "decision": decision, "report": REPORT_JSON, "recommended_next_action": action["command"]}
