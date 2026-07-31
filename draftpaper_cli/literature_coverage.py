"""Role-based literature coverage review for the public workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project


ROLE_NAMES = ("problem_gap", "data_provenance", "method", "evaluation_standard", "baseline", "limitations")


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _roles(item: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    contexts = {str(value).lower() for value in (item.get("search_contexts") or [item.get("search_context") or "idea"])}
    if contexts & {"idea", "introduction"}:
        roles.add("problem_gap")
    if "data" in contexts:
        roles.add("data_provenance")
    if "methods" in contexts:
        roles.add("method")
    text = " ".join(str(item.get(key) or "") for key in ("title", "abstract", "evidence_notes")).lower()
    if any(token in text for token in ("metric", "evaluation", "benchmark", "statistical", "confidence interval")):
        roles.add("evaluation_standard")
    if any(token in text for token in ("baseline", "comparison", "state of the art", "benchmark")):
        roles.add("baseline")
    if any(token in text for token in ("limitation", "uncertainty", "future work", "caveat")):
        roles.add("limitations")
    return roles


def review_literature_coverage(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    references_dir = state.path / "references"
    items = _read_json(references_dir / "literature_items.json", [])
    if isinstance(items, dict):
        items = items.get("items", [])
    items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    counts = {role: 0 for role in ROLE_NAMES}
    source_counts: dict[str, int] = {}
    records = []
    for item in items:
        source_types = set()
        for record in item.get("source_records") or []:
            if isinstance(record, dict) and record.get("source_type"):
                source_types.add(str(record["source_type"]))
        source_types.update(str(value) for value in (item.get("source_type"), item.get("reference_origin")) if value)
        for source_type in source_types:
            source_counts[source_type] = source_counts.get(source_type, 0) + 1
        roles = sorted(_roles(item))
        for role in roles:
            counts[role] += 1
        records.append({"citation_key": item.get("bibtex_key", ""), "title": item.get("title", ""), "roles": roles, "source_types": sorted(source_types)})
    gaps = [role for role, count in counts.items() if count == 0]
    provider_report = _read_json(references_dir / "search_queries.json", {}).get("provider_router", {})
    report = {
        "schema_version": "dpl.literature_coverage.v1",
        "status": "review_required" if gaps else "covered",
        "item_count": len(items),
        "role_counts": counts,
        "source_counts": source_counts,
        "gaps": gaps,
        "provider_router": provider_report,
        "records": records,
        "policy": "role_based_review_not_total_count_gate",
    }
    _write_json(references_dir / "literature_coverage.json", report)
    lines = ["# Literature Coverage Review", "", f"Status: **{report['status']}**", f"References: **{len(items)}**", "", "## Role coverage", "", "| Role | Count |", "|---|---:|"]
    lines.extend(f"| {role} | {counts[role]} |" for role in ROLE_NAMES)
    lines.extend(["", "## Source coverage", "", "| Source type | Count |", "|---|---:|"])
    lines.extend(f"| {source} | {count} |" for source, count in sorted(source_counts.items()))
    if gaps:
        lines.extend(["", "## Gaps requiring user review", "", *[f"- `{gap}` has no supporting reference role in the current pool." for gap in gaps]])
    lines.extend(["", "This report identifies missing roles; it does not auto-cite a reference or claim that a provider failure proves absence of literature.", ""])
    (references_dir / "literature_coverage.md").write_text("\n".join(lines), encoding="utf-8")
    return {"status": report["status"], "project_path": str(state.path), "output": "references/literature_coverage.json", "markdown": "references/literature_coverage.md", "gaps": gaps, "role_counts": counts, "source_counts": source_counts}

