# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Prepare minimal, evidence-preserving Results prose repairs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


PLAN_JSON = "review/results_semantic_repair_plan.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_results_semantic_repair(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    review = _read_json(state.path / "review" / "result_discipline_review_report.json")
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml")
    semantic_issues = [item for item in (review.get("results_semantic_audit") or {}).get("issues") or [] if isinstance(item, dict)]
    quality_issues = [item for item in (review.get("manuscript_quality") or {}).get("issues") or [] if isinstance(item, dict)]
    tasks = []
    seen = set()
    for issue in [*semantic_issues, *quality_issues]:
        detail_text = str(issue.get("detail") or "")
        metric_match = re.search(r"\b(auc|f1|accuracy|r2|rmse|mae)\b", detail_text, flags=re.I)
        value_match = re.search(r"[-+]?\d+(?:\.\d+)?", detail_text)
        metric_name = str(issue.get("metric_name") or (metric_match.group(1).lower() if metric_match else ""))
        metric_value = str(issue.get("value") if issue.get("value") is not None else (value_match.group(0) if value_match else detail_text))
        key = (str(issue.get("kind")), metric_name, metric_value)
        if key in seen:
            continue
        seen.add(key)
        kind = str(issue.get("kind") or "results_semantic_issue")
        priority = ["rewrite_claim", "narrow_claim", "remove_unsupported_metric_clause"] if kind == "untraceable_metric_claim" else ["rewrite_claim", "remove_internal_language"]
        tasks.append({
            "task_id": f"results_semantic_repair_{len(tasks) + 1:02d}",
            "kind": kind,
            "detail": issue.get("detail") or issue,
            "repair_priority": priority,
            "forbid_full_section_regeneration": True,
            "preserve": ["verified_figure_narrative", "verified_metrics", "sample_boundary", "baseline_ablation_uncertainty_reasoning"],
            "verified_metrics": run_manifest.get("metrics") or {},
            "instruction": "Edit only the affected claim span. Prefer a truthful rewrite supported by existing evidence; do not replace the whole Results section with deterministic fallback prose.",
        })
    payload = {
        "status": "written",
        "schema_version": "dpl.results_semantic_repair.v1",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "source_review": "review/result_discipline_review_report.json",
        "tasks": tasks,
        "recommended_next_command": "prepare-section-writing",
        "recommended_cli": f'python -m draftpaper_cli.cli prepare-section-writing --project "{state.path}" --section results',
        "completion_sequence": ["prepare-section-writing", "submit-section-draft", "write-results", "review-results-with-discipline-rules"],
    }
    _write_json(state.path / PLAN_JSON, payload)
    return {"status": "written", "project_path": str(state.path), "task_count": len(tasks), "repair_plan": PLAN_JSON}
