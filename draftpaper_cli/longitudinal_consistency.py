"""Cross-revision scientific fact and manuscript consistency auditing."""

from __future__ import annotations

import hashlib
import html
import json
import fnmatch
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .canonical_fact_registry import load_fact_registry
from .passport import project_root, utc_now
from .revision_cycle import load_active_revision_cycle
from .scientific_baseline import load_active_baseline
from .state_kernel import atomic_write_json, atomic_write_text


REPORT_SCHEMA = "dpl.longitudinal_consistency_report.v1"
REPORT_DIR = "review/consistency"


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _identity(fact: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(fact.get(key) for key in ("entity_type", "cohort_id", "run_id", "validation_design_id", "sample_unit"))


def compare_fact_registries(parent: dict[str, Any] | None, current: dict[str, Any] | None) -> list[dict[str, Any]]:
    before = {str(item.get("fact_id")): item for item in (parent or {}).get("facts") or [] if isinstance(item, dict)}
    after = {str(item.get("fact_id")): item for item in (current or {}).get("facts") or [] if isinstance(item, dict)}
    rows: list[dict[str, Any]] = []
    for fact_id in sorted(set(before) | set(after)):
        old = before.get(fact_id)
        new = after.get(fact_id)
        if old is None:
            rows.append({"fact_id": fact_id, "status": "added", "before": None, "after": new, "reason": "new fact in current revision"})
            continue
        if new is None:
            rows.append({"fact_id": fact_id, "status": "superseded", "before": old, "after": None, "reason": "fact is absent from current active registry"})
            continue
        if _identity(old) != _identity(new):
            status = "non_comparable"
            reason = "same fact id is bound to a different cohort/run/validation identity"
        elif old.get("value") != new.get("value") or old.get("unit") != new.get("unit") or old.get("uncertainty") != new.get("uncertainty"):
            status = "conflict"
            reason = "same identity has different value, unit, or uncertainty"
        else:
            status = "unchanged"
            reason = "same fact identity and value"
        rows.append({"fact_id": fact_id, "status": status, "before": old, "after": new, "reason": reason})
    return rows


def _extract_text_fact_mentions(root: Path, fact_ids: set[str]) -> list[dict[str, Any]]:
    """Find explicit fact IDs in manuscript-like text without interpreting prose."""

    rows: list[dict[str, Any]] = []
    for directory in ("latex", "writing", "results", "discussion", "introduction", "data_writing", "methods_writing"):
        path = root / directory
        if not path.is_dir():
            continue
        for file in path.rglob("*"):
            if not file.is_file() or file.suffix.lower() not in {".tex", ".md", ".txt", ".json", ".yaml", ".yml", ".csv"}:
                continue
            try:
                text = file.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            for fact_id in sorted(fact_ids):
                if fact_id in text:
                    rows.append({"fact_id": fact_id, "path": file.relative_to(root).as_posix(), "status": "referenced", "evidence_ref": f"artifact:{file.relative_to(root).as_posix()}"})
    return rows


def _consumer_conflicts(
    *,
    parent: dict[str, Any] | None,
    current: dict[str, Any] | None,
    mentions: list[dict[str, Any]],
    protected_facts: set[str],
) -> list[dict[str, Any]]:
    before = {str(item.get("fact_id")): item for item in (parent or {}).get("facts") or [] if isinstance(item, dict)}
    after = {str(item.get("fact_id")): item for item in (current or {}).get("facts") or [] if isinstance(item, dict)}
    by_fact: dict[str, list[dict[str, Any]]] = {}
    for mention in mentions:
        by_fact.setdefault(str(mention.get("fact_id") or ""), []).append(mention)
    issues: list[dict[str, Any]] = []
    for fact_id, old in before.items():
        new = after.get(fact_id)
        fact_mentions = by_fact.get(fact_id, [])
        if (old.get("must_preserve") or fact_id in protected_facts) and (
            new is None
            or new.get("value") != old.get("value")
            or _identity(new) != _identity(old)
        ):
            issues.append(
                {
                    "fact_id": fact_id,
                    "status": "protected_fact_changed",
                    "reason": "A protected or must-preserve fact changed, disappeared, or changed identity in this revision.",
                }
            )
        if new is None and fact_mentions:
            issues.append(
                {
                    "fact_id": fact_id,
                    "status": "superseded_fact_consumed",
                    "reason": "A fact from the parent registry is absent from the current registry but is still referenced by a manuscript-facing artifact.",
                    "paths": [item.get("path") for item in fact_mentions],
                }
            )
    for fact_id, fact in after.items():
        fact_mentions = by_fact.get(fact_id, [])
        if fact.get("status") in {"superseded", "withdrawn"} and fact_mentions:
            issues.append(
                {
                    "fact_id": fact_id,
                    "status": "superseded_fact_consumed",
                    "reason": "A superseded or withdrawn fact is still referenced by a manuscript-facing artifact.",
                    "paths": [item.get("path") for item in fact_mentions],
                }
            )
        allowed = [str(item) for item in fact.get("allowed_consumers") or [] if str(item).strip()]
        if allowed:
            for mention in fact_mentions:
                path = str(mention.get("path") or "")
                if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed):
                    issues.append(
                        {
                            "fact_id": fact_id,
                            "status": "fact_consumer_outside_contract",
                            "reason": "The fact is consumed by an artifact outside its allowed_consumer contract.",
                            "path": path,
                            "allowed_consumers": allowed,
                        }
                    )
    return issues


def audit_longitudinal_consistency(project: str | Path, *, output_root: str | Path | None = None) -> dict[str, Any]:
    root = project_root(project)
    current_baseline = load_active_baseline(root)
    cycle = load_active_revision_cycle(root)
    current_registry = load_fact_registry(root)
    parent_registry = None
    if current_baseline and current_baseline.get("parent_baseline_id"):
        parent_baseline_path = root / "lineage/scientific_baselines" / f"{current_baseline['parent_baseline_id']}.json"
        try:
            parent_baseline = json.loads(parent_baseline_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            parent_baseline = {}
        parent_registry_id = parent_baseline.get("canonical_fact_registry_id") if isinstance(parent_baseline, dict) else None
        if parent_registry_id:
            from .canonical_fact_registry import load_fact_registry as _load_registry

            parent_registry = _load_registry(root, str(parent_registry_id))
    rows = compare_fact_registries(parent_registry, current_registry)
    fact_ids = {str(item.get("fact_id")) for item in (current_registry or {}).get("facts") or [] if item.get("fact_id")}
    fact_ids.update({str(item.get("fact_id")) for item in (parent_registry or {}).get("facts") or [] if item.get("fact_id")})
    mentions = _extract_text_fact_mentions(root, fact_ids)
    conflicts = [row for row in rows if row.get("status") == "conflict"]
    non_comparable = [row for row in rows if row.get("status") == "non_comparable"]
    unresolved = [row for row in rows if row.get("status") in {"added", "superseded"}]
    protected_facts = {str(item) for item in (cycle or {}).get("protected_facts") or [] if str(item).strip()}
    consumer_conflicts = _consumer_conflicts(
        parent=parent_registry,
        current=current_registry,
        mentions=mentions,
        protected_facts=protected_facts,
    )
    baseline_issues: list[dict[str, Any]] = []
    if current_baseline is None:
        baseline_issues.append({"status": "baseline_missing", "reason": "No immutable scientific baseline is active for this project."})
    elif current_registry and current_baseline.get("canonical_fact_registry_id") not in {None, current_registry.get("registry_id")}:
        baseline_issues.append({"status": "baseline_registry_mismatch", "reason": "The active fact registry is not the registry bound by the active scientific baseline."})
    status = "blocked" if conflicts or consumer_conflicts else "needs_review" if non_comparable or unresolved or baseline_issues else "passed"
    report = {
        "schema_version": REPORT_SCHEMA,
        "report_id": "consistency-" + _hash({"rows": rows, "mentions": mentions})[:20],
        "project_id": _project_id(root),
        "revision_cycle_id": (cycle or {}).get("revision_cycle_id"),
        "current_baseline_id": (current_baseline or {}).get("baseline_id"),
        "parent_baseline_id": (current_baseline or {}).get("parent_baseline_id"),
        "status": status,
        "fact_change_matrix": rows,
        "cross_artifact_fact_mentions": mentions,
        "cross_artifact_conflicts": consumer_conflicts,
        "baseline_issues": baseline_issues,
        "conflicts": conflicts,
        "non_comparable": non_comparable,
        "unresolved": unresolved,
        "recovery_plan": {
            "recommended_route": "reopen_scientific_stage" if conflicts or consumer_conflicts else "review_revision_scope" if status != "passed" else "continue",
            "requires_human_confirmation": bool(conflicts or consumer_conflicts),
            "reason": "same canonical fact identity conflicts or a protected/superseded fact is consumed" if conflicts or consumer_conflicts else None,
        },
        "created_at": utc_now(),
    }
    report["report_sha256"] = _hash(report)
    output_dir = Path(output_root) if output_root else root / REPORT_DIR / str(report["revision_cycle_id"] or "unscoped")
    output_dir = output_dir if output_dir.is_absolute() else root / output_dir
    try:
        output_dir.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Longitudinal consistency output must remain inside the project.") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "longitudinal_consistency_report.json"
    atomic_write_json(report_path, report)
    matrix_lines = ["fact_id,status,reason"]
    for row in rows:
        reason = str(row.get("reason") or "").replace('"', '""')
        matrix_lines.append(f"{row.get('fact_id')},{row.get('status')},\"{reason}\"")
    atomic_write_text(output_dir / "fact_change_matrix.csv", "\n".join(matrix_lines) + "\n")
    atomic_write_text(output_dir / "cross_artifact_conflicts.csv", "fact_id,status,reason\n" + "\n".join(f"{row.get('fact_id')},{row.get('status')},\"{str(row.get('reason') or '').replace(chr(34), chr(34)*2)}\"" for row in [*conflicts, *non_comparable, *consumer_conflicts, *baseline_issues]) + "\n")
    recovery = report["recovery_plan"]
    atomic_write_json(output_dir / "recovery_plan.json", recovery)
    html_rows = "".join(f"<tr><td>{html.escape(str(row.get('fact_id')))}</td><td>{html.escape(str(row.get('status')))}</td><td>{html.escape(str(row.get('reason')))}</td></tr>" for row in rows)
    atomic_write_text(output_dir / "longitudinal_consistency_report.zh-CN.html", f"<!doctype html><meta charset='utf-8'><title>纵向一致性审计</title><h1>纵向一致性审计</h1><p>状态：{html.escape(status)}</p><table border='1'><tr><th>fact_id</th><th>状态</th><th>说明</th></tr>{html_rows}</table>")
    return {"status": status, "project_path": str(root), "report": report, "report_path": str(report_path.resolve()), "html_path": str((output_dir / "longitudinal_consistency_report.zh-CN.html").resolve()), "recovery_plan": recovery}


def _project_id(root: Path) -> str | None:
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = ["REPORT_SCHEMA", "audit_longitudinal_consistency", "compare_fact_registries"]
