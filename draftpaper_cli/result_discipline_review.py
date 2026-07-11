# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Post-Results composite-discipline review-rule audit."""

from __future__ import annotations

import json
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
    evidence_context = {
        "available_evidence_roles": ["results_prose", "figure_plugin_trace", "plugin_binding_plan"],
        "figure_plugin_trace_decision": trace.get("decision"),
        "bound_review_rule_ids": [
            item.get("plugin_id") for item in bindings.get("bindings") or []
            if isinstance(item, dict) and item.get("kind") == "review"
        ],
    }
    rule_gate = assess_review_rules(
        state.path,
        stage="assess_result_validity",
        evidence_context=evidence_context,
        write_path=state.path / "review" / "result_discipline_review_rule_gate.json",
    )
    if trace.get("decision") != "pass":
        decision = "revise_required"
        action = {
            "command": "prepare-plugin-rescue" if trace.get("decision") == "blocked" else "verify-methods",
            "reason": "Results cannot be accepted until every main figure has a complete claim, plugin, verified run-output, and review-rule trace.",
        }
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
        "recommended_next_action": action,
        "policy": "Citation audit occurs only after final manuscript sections; this review checks scientific evidence and result claims without deleting references.",
    }
    _write_json(state.path / REPORT_JSON, report)
    write_html_report(state.path / REPORT_HTML, _render(report), title="Results Discipline Review")
    return {"status": "written", "project_path": str(state.path), "decision": decision, "report": REPORT_JSON, "recommended_next_action": action["command"]}
