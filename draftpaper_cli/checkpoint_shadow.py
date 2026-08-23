"""Read-only v5 checkpoint shadow audits for existing projects."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import build_human_decision_brief, validate_human_decision_brief
from .checkpoint_fingerprint import build_scientific_decision_fingerprint, fingerprint_has_method_analysis_identity
from .figure_claim_map import build_figure_claim_map, validate_figure_claim_map
from .passport import project_root, utc_now
from .state_kernel import atomic_write_json, atomic_write_text

SHADOW_REPORT_SCHEMA = "dpl.checkpoint_v5_shadow_report.v1"
V6_SHADOW_REPORT_SCHEMA = "dpl.checkpoint_v6_shadow_report.v1"
_PROTECTED_FILES = (
    "project.json",
    "project_passport.yaml",
    "checkpoint_ledger.jsonl",
    "results/promoted_evidence_snapshot.json",
    "latex/main.pdf",
)
_LEGACY_SUMMARY_SCHEMAS = frozenset({
    "dpl.checkpoint_summary.v1",
    "dpl.checkpoint_summary.v2",
    "dpl.checkpoint_summary.v3",
    "dpl.checkpoint_summary.v4",
})
_SCHEMA_PATTERN = re.compile(r'"schema_version"\s*:\s*"([^"\\]+)"')


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _protected_snapshot(root: Path) -> dict[str, Any]:
    files = {relative: _file_hash(root / relative) for relative in _PROTECTED_FILES}
    checkpoint_files: dict[str, str | None] = {}
    checkpoints = root / "review" / "checkpoints"
    if checkpoints.is_dir():
        for path in sorted(checkpoints.rglob("stage_summary.json")):
            checkpoint_files[path.relative_to(root).as_posix()] = _file_hash(path)
        for path in sorted(checkpoints.rglob("review_decision_receipt.json")):
            checkpoint_files[path.relative_to(root).as_posix()] = _file_hash(path)
    return {"protected_files": files, "checkpoint_records": checkpoint_files}


def _records(root: Path) -> list[dict[str, Any]]:
    from .checkpoint_summary import _checkpoint_index_records

    return _checkpoint_index_records(root)


def _summary(root: Path, record: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    relative = str(record.get("stage_summary_json") or "").replace("\\", "/")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return None, None
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return path, None
    return path, payload if isinstance(payload, dict) else None


def _summary_schema(path: Path | None) -> str | None:
    """Read only the JSON header when a legacy package needs no projection.

    Historical projects can contain hundreds of multi-megabyte v1-v4 summary
    files.  A shadow run must prove that it does not mutate them, not eagerly
    deserialize their complete audit payload.  The exact single-package
    migration command still performs a full validation when an owner chooses
    to migrate that checkpoint.
    """

    if path is None:
        return None
    try:
        with path.open("rb") as handle:
            # A fixed byte window can end inside a UTF-8 sequence.  Ignoring
            # only that incomplete tail preserves the ASCII schema header
            # without deserializing a multi-megabyte legacy package.
            header = handle.read(64 * 1024).decode("utf-8-sig", errors="ignore")
    except OSError:
        return None
    match = _SCHEMA_PATTERN.search(header)
    return match.group(1) if match else None


def _pre_figure_claim_fingerprint(summary: dict[str, Any]) -> bool:
    """Return whether a v5 package predates FigureClaimMap-bound science IDs."""

    fingerprint = summary.get("scientific_decision_fingerprint")
    payload = fingerprint.get("canonical_payload") if isinstance(fingerprint, dict) else None
    return not (
        isinstance(payload, dict)
        and isinstance(payload.get("figure_claim_map"), list)
        and isinstance(summary.get("scientific_figure_claim_sha256"), str)
        and bool(str(summary.get("scientific_figure_claim_sha256") or "").strip())
    )


def _pre_method_analysis_fingerprint(summary: dict[str, Any]) -> bool:
    if str(summary.get("checkpoint_type") or summary.get("completed_stage") or "") != "core_evidence":
        return False
    fingerprint = summary.get("scientific_decision_fingerprint")
    return not fingerprint_has_method_analysis_identity(fingerprint if isinstance(fingerprint, dict) else {})


def _safe_output_root(root: Path, output_root: str | Path | None) -> Path:
    if output_root is None:
        target = Path(tempfile.gettempdir()) / f"draftpaper-v5-shadow-{root.name}-{utc_now().replace(':', '').replace('+00:00', 'Z')}"
    else:
        target = Path(output_root).expanduser().resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return target
    raise ValueError("A read-only shadow report must be written outside the project directory.")


def _render_html(report: dict[str, Any]) -> str:
    rows = []
    for item in report.get("checkpoints") or []:
        rows.append(
            "<tr>"
            f"<td>{item.get('checkpoint_id') or ''}</td>"
            f"<td>{item.get('summary_schema') or ''}</td>"
            f"<td>{item.get('status') or ''}</td>"
            f"<td>{'；'.join(item.get('reason_codes') or [])}</td>"
            "</tr>"
        )
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Draftpaper-loop v5 checkpoint 只读 shadow 回归</title>
<style>body{{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f6f8fb;color:#172033}}main{{max-width:980px;margin:0 auto;padding:24px 16px}}section{{background:#fff;border:1px solid #d4dce7;padding:16px;margin-top:14px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #d4dce7;padding:8px;text-align:left;overflow-wrap:anywhere}}code{{overflow-wrap:anywhere}}</style>
</head><body><main><h1>v5 checkpoint 只读 shadow 回归</h1>
<section><p>项目：<code>{report.get('project_path')}</code></p><p>状态：<strong>{report.get('status')}</strong></p><p>本次只读取项目；报告输出位于项目外，未写入 project.json、passport、ledger、checkpoint、evidence snapshot 或 main.pdf。</p></section>
<section><h2>Checkpoint 审计</h2><table><thead><tr><th>ID</th><th>合同</th><th>状态</th><th>说明</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
</main></body></html>\n'''


def shadow_checkpoint_v5(project: str | Path, *, output_root: str | Path | None = None) -> dict[str, Any]:
    """Audit existing checkpoint packages without mutating a project.

    The report is deliberately written outside the project root and records a
    before/after digest of all state objects that shadow regression is not
    allowed to alter.
    """

    root = project_root(project)
    target = _safe_output_root(root, output_root)
    before = _protected_snapshot(root)
    entries: list[dict[str, Any]] = []
    for record in _records(root):
        path: Path | None = None
        relative = str(record.get("stage_summary_json") or "").replace("\\", "/")
        if relative and not Path(relative).is_absolute() and ".." not in Path(relative).parts:
            path = root / relative
        schema = _summary_schema(path)
        if schema is None:
            entries.append(
                {
                    "checkpoint_id": record.get("checkpoint_id"),
                    "summary_schema": None,
                    "status": "invalid",
                    "reason_codes": ["summary_missing_or_invalid"],
                }
            )
            continue
        if schema in _LEGACY_SUMMARY_SCHEMAS:
            entries.append(
                {
                    "checkpoint_id": record.get("checkpoint_id"),
                    "summary_schema": schema,
                    "status": "legacy_read_only",
                    "reason_codes": ["legacy_summary_requires_explicit_v5_checkpoint"],
                    "migration_action": "run_audit_checkpoint_v5_migration_before_creating_v5",
                    "summary_path": str(path.resolve()) if path and path.is_file() else None,
                }
            )
            continue
        if schema != "dpl.checkpoint_summary.v5":
            entries.append(
                {
                    "checkpoint_id": record.get("checkpoint_id"),
                    "summary_schema": schema,
                    "status": "invalid",
                    "reason_codes": ["unsupported_summary_schema"],
                    "summary_path": str(path.resolve()) if path and path.is_file() else None,
                }
            )
            continue
        path, summary = _summary(root, record)
        if summary is None:
            entries.append(
                {
                    "checkpoint_id": record.get("checkpoint_id"),
                    "summary_schema": schema,
                    "status": "invalid",
                    "reason_codes": ["summary_missing_or_invalid"],
                }
            )
            continue
        if schema == "dpl.checkpoint_summary.v5":
            if _pre_figure_claim_fingerprint(summary):
                entries.append(
                    {
                        "checkpoint_id": summary.get("checkpoint_id") or record.get("checkpoint_id"),
                        "summary_schema": schema,
                        "status": "legacy_read_only",
                        "reason_codes": ["legacy_v5_pre_figure_claim_fingerprint"],
                        "migration_action": "create_new_v5_checkpoint_and_request_c3",
                        "summary_path": str(path.resolve()) if path else None,
                    }
                )
                continue
            if _pre_method_analysis_fingerprint(summary):
                entries.append(
                    {
                        "checkpoint_id": summary.get("checkpoint_id") or record.get("checkpoint_id"),
                        "summary_schema": schema,
                        "status": "legacy_read_only",
                        "reason_codes": ["legacy_v5_pre_method_analysis_fingerprint"],
                        "migration_action": "create_new_v5_checkpoint_and_request_c3",
                        "summary_path": str(path.resolve()) if path else None,
                    }
                )
                continue
            brief = build_human_decision_brief(summary)
            figure_map = build_figure_claim_map(summary, brief)
            fingerprint = build_scientific_decision_fingerprint(summary, brief, figure_claim_map=figure_map)
            stored = summary.get("scientific_decision_fingerprint") if isinstance(summary.get("scientific_decision_fingerprint"), dict) else {}
            problems = validate_human_decision_brief(brief)
            problems.extend(item["code"] for item in validate_figure_claim_map(figure_map))
            if fingerprint.get("scientific_decision_sha256") != stored.get("scientific_decision_sha256"):
                problems.append("scientific_fingerprint_projection_mismatch")
            if figure_map.get("scientific_figure_claim_sha256") != summary.get("scientific_figure_claim_sha256"):
                problems.append("scientific_figure_claim_projection_mismatch")
            entries.append(
                {
                    "checkpoint_id": summary.get("checkpoint_id") or record.get("checkpoint_id"),
                    "summary_schema": schema,
                    "status": "passed" if not problems else "invalid",
                    "reason_codes": problems,
                    "summary_path": str(path.resolve()) if path else None,
                    "scientific_decision_sha256": stored.get("scientific_decision_sha256"),
                }
            )
            continue
    after = _protected_snapshot(root)
    project_unchanged = before == after
    status = "passed" if entries and project_unchanged and all(item.get("status") in {"passed", "legacy_read_only"} for item in entries) else "blocked"
    report = {
        "schema_version": SHADOW_REPORT_SCHEMA,
        "project_path": str(root),
        "generated_at": utc_now(),
        "mode": "read_only_shadow",
        "checkpoint_count": len(entries),
        "checkpoints": entries,
        "project_state_unchanged": project_unchanged,
        "protected_state_before_sha256": _hash(before),
        "protected_state_after_sha256": _hash(after),
        "status": status,
    }
    report["report_sha256"] = _hash({key: value for key, value in report.items() if key != "report_sha256"})
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "checkpoint_v5_shadow_report.json"
    html_path = target / "checkpoint_v5_shadow_report.zh-CN.html"
    atomic_write_json(json_path, report)
    atomic_write_text(html_path, _render_html(report))
    return {
        "status": status,
        "project_path": str(root),
        "report": report,
        "report_json": str(json_path.resolve()),
        "report_html": str(html_path.resolve()),
    }


def shadow_checkpoint_v6(project: str | Path, *, output_root: str | Path | None = None) -> dict[str, Any]:
    """Verify v6 packages without changing project state or package files.

    v1-v5 packages are intentionally reported as historical read-only records.
    This makes the shadow result suitable for a release gate: it can prove
    that a real project is safe to inspect while refusing to silently upgrade
    any earlier author decision.
    """

    from .checkpoint_summary import validate_checkpoint_summary

    root = project_root(project)
    target = _safe_output_root(root, output_root)
    before = _protected_snapshot(root)
    entries: list[dict[str, Any]] = []
    for record in _records(root):
        path: Path | None = None
        relative = str(record.get("stage_summary_json") or "").replace("\\", "/")
        if relative and not Path(relative).is_absolute() and ".." not in Path(relative).parts:
            path = root / relative
        schema = _summary_schema(path)
        base = {
            "checkpoint_id": record.get("checkpoint_id"),
            "summary_schema": schema,
            "summary_path": str(path.resolve()) if path and path.is_file() else None,
        }
        if schema is None:
            entries.append({**base, "status": "invalid", "reason_codes": ["summary_missing_or_invalid"]})
            continue
        if schema != "dpl.checkpoint_summary.v6":
            entries.append(
                {
                    **base,
                    "status": "legacy_read_only",
                    "reason_codes": ["historical_checkpoint_requires_explicit_v6_recheck"],
                    "migration_action": "create_new_v6_checkpoint_and_request_c3",
                }
            )
            continue
        validation = validate_checkpoint_summary(root, record)
        entries.append(
            {
                **base,
                "status": "passed" if validation.get("valid") else "invalid",
                "reason_codes": [str(item) for item in validation.get("reasons") or []],
                "scientific_decision_sha256": record.get("scientific_decision_sha256"),
            }
        )
    after = _protected_snapshot(root)
    project_unchanged = before == after
    status = "passed" if entries and project_unchanged and all(item.get("status") in {"passed", "legacy_read_only"} for item in entries) else "blocked"
    report = {
        "schema_version": V6_SHADOW_REPORT_SCHEMA,
        "project_path": str(root),
        "generated_at": utc_now(),
        "mode": "read_only_shadow",
        "checkpoint_count": len(entries),
        "checkpoints": entries,
        "project_state_unchanged": project_unchanged,
        "protected_state_before_sha256": _hash(before),
        "protected_state_after_sha256": _hash(after),
        "status": status,
    }
    report["report_sha256"] = _hash({key: value for key, value in report.items() if key != "report_sha256"})
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "checkpoint_v6_shadow_report.json"
    html_path = target / "checkpoint_v6_shadow_report.zh-CN.html"
    atomic_write_json(json_path, report)
    atomic_write_text(html_path, _render_html(report).replace("v5 checkpoint", "v6 checkpoint"))
    return {
        "status": status,
        "project_path": str(root),
        "report": report,
        "report_json": str(json_path.resolve()),
        "report_html": str(html_path.resolve()),
    }


__all__ = ["SHADOW_REPORT_SCHEMA", "V6_SHADOW_REPORT_SCHEMA", "shadow_checkpoint_v5", "shadow_checkpoint_v6"]
