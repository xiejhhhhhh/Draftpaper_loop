"""Unified human-checkpoint summaries and Chinese offline review pages."""

from __future__ import annotations

import hashlib
import json
import os
import re
from html import escape
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .execution_policy import redact_sensitive
from .passport import collect_artifacts, project_root, read_jsonl, utc_now
from .state_kernel import atomic_write_json, atomic_write_text


CHECKPOINT_SUMMARY_SCHEMA = "dpl.checkpoint_summary.v1"
ARTIFACT_MANIFEST_SCHEMA = "dpl.checkpoint_artifact_manifest.v1"
CONFIRMATION_REQUEST_SCHEMA = "dpl.confirmation_request.v1"
CHANGE_REPORT_SCHEMA = "dpl.checkpoint_change_report.v1"
UNRESOLVED_ISSUES_SCHEMA = "dpl.checkpoint_unresolved_issues.v1"
AGENT_PAYLOAD_SCHEMA = "dpl.checkpoint_agent_payload.v1"
CHECKPOINT_ROOT = "review/checkpoints"

_STAGE_TITLES = {
    "research_plan": "研究蓝图与可行性确认",
    "research_plan_feasibility": "研究蓝图可行性确认",
    "data": "数据来源与数据质量确认",
    "method_plan": "方法与统计合同确认",
    "methods": "方法运行与复现证据确认",
    "result_support": "结果支撑与论断路线确认",
    "core_evidence": "关键结果与论断支撑确认",
    "plugin": "科研插件候选与许可证确认",
    "quality_checks": "最终稿与发布确认",
    "writing": "论文内容补全确认",
}

_STAGE_PREFIXES = {
    "research_plan": ("research_plan/", "journal_profile/", "plugins/"),
    "research_plan_feasibility": ("research_plan/", "data/", "methods/", "review/"),
    "data": ("data/", "review/"),
    "method_plan": ("methods/", "research_plan/", "review/"),
    "methods": ("methods/", "code/", "results/", "review/"),
    "result_support": ("results/", "review/", "methods/", "data/"),
    "core_evidence": ("core_evidence/", "results/", "review/"),
    "plugin": ("plugins/", "research_plan/", "review/"),
    "quality_checks": ("quality_checks/", "quality/", "integrity/", "citation_audit/", "review/", "latex/"),
    "writing": ("writing/", "latex/", "review/"),
}

_PATH_KEY_TOKENS = (
    "path",
    "file",
    "report",
    "manifest",
    "artifact",
    "output",
    "html",
    "json",
    "packet",
)


class CheckpointSummaryError(RuntimeError):
    """Raised when a reviewable checkpoint summary cannot be committed."""


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload, volatile_fields=frozenset({"created_at", "generated_at"})).encode("utf-8")).hexdigest()


def _relative_project_path(root: Path, raw: str) -> str | None:
    candidate = Path(str(raw).strip().strip('"'))
    if not str(candidate) or "://" in str(candidate):
        return None
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return None
    normalized = str(candidate).replace("\\", "/").lstrip("./")
    if not normalized or normalized == "." or normalized.startswith("../"):
        return None
    if (root / normalized).exists():
        return normalized
    return None


def _payload_paths(root: Path, payload: Any) -> list[str]:
    found: set[str] = set()

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if not isinstance(value, str) or not any(token in key.lower() for token in _PATH_KEY_TOKENS):
            return
        relative = _relative_project_path(root, value)
        if relative:
            found.add(relative)

    visit(payload)
    return sorted(found)


def _in_stage_scope(relative: str, stage: str) -> bool:
    prefixes = _STAGE_PREFIXES.get(stage, (f"{stage}/",))
    return relative.replace("\\", "/").startswith(prefixes)


def _stage_artifacts(root: Path, stage: str, explicit_paths: list[str], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in artifacts:
        relative = str(item.get("path") or "").replace("\\", "/")
        if relative in explicit_paths or _in_stage_scope(relative, stage):
            selected.append(item)
    for relative in explicit_paths:
        if not any(str(item.get("path")) == relative for item in selected):
            selected.append({"path": relative, "missing": not (root / relative).is_file()})
    return sorted(selected, key=lambda item: str(item.get("path") or ""))[:160]


def _artifact_manifest(
    root: Path,
    stage: str,
    explicit_paths: list[str],
    before_artifacts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    before = {str(item.get("path")): item for item in before_artifacts or [] if isinstance(item, dict)}
    current = collect_artifacts(root)
    rows: list[dict[str, Any]] = []
    for item in _stage_artifacts(root, stage, explicit_paths, current):
        relative = str(item.get("path") or "")
        previous = before.get(relative)
        if item.get("missing"):
            operation = "failed"
            semantic_changed = None
        elif previous is None:
            operation = "generated"
            semantic_changed = True
        elif (previous.get("byte_sha256") or previous.get("sha256")) != (item.get("byte_sha256") or item.get("sha256")):
            operation = "modified"
            semantic_changed = previous.get("semantic_sha256") != item.get("semantic_sha256")
        else:
            operation = "unchanged"
            semantic_changed = False
        rows.append(
            {
                "artifact_id": item.get("artifact_id") or hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16],
                "project_relative_path": relative,
                "artifact_role": item.get("stage") or "unknown",
                "operation": operation,
                "before_byte_sha256": previous.get("byte_sha256") or previous.get("sha256") if previous else None,
                "after_byte_sha256": item.get("byte_sha256") or item.get("sha256"),
                "before_semantic_sha256": previous.get("semantic_sha256") if previous else None,
                "after_semantic_sha256": item.get("semantic_sha256"),
                "evidence_sha256": item.get("evidence_sha256"),
                "semantic_changed": semantic_changed,
                "user_attention": "required" if operation in {"generated", "modified", "failed"} else "informational",
            }
        )
    return {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA,
        "checkpoint_stage": stage,
        "artifacts": rows,
    }


def _payload_items(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        values.extend(value if isinstance(value, list) else [value])
    return values


def _short_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): redact_sensitive(item) for key, item in value.items() if key not in {"absolute_path", "project_path"}}
    return {"summary_zh": redact_sensitive(str(value))}


def _decision_status(payload: dict[str, Any]) -> str:
    return str(payload.get("decision") or payload.get("status") or "completed").lower()


def _scientific_summary(stage: str, command: str, payload: dict[str, Any]) -> list[str]:
    status = _decision_status(payload)
    title = _STAGE_TITLES.get(stage, stage)
    summary = [f"{title}阶段命令 `{command}` 已返回状态 `{status}`。"]
    for key in ("reason", "message", "summary", "scientific_summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            summary.append(redact_sensitive(value.strip()))
        elif isinstance(value, list):
            summary.extend(redact_sensitive(str(item)) for item in value[:3])
    next_action = payload.get("next_action")
    if isinstance(next_action, dict) and next_action.get("reason"):
        summary.append(f"下一步：{redact_sensitive(str(next_action['reason']))}")
    return summary[:8]


def _inspection_targets(manifest: dict[str, Any], explicit_paths: list[str], root: Path) -> list[dict[str, str]]:
    rows = manifest.get("artifacts") or []
    ordered = [*explicit_paths, *[str(item.get("project_relative_path")) for item in rows if item.get("operation") in {"generated", "modified", "failed"}]]
    seen: set[str] = set()
    targets: list[dict[str, str]] = []
    for relative in ordered:
        if not relative or relative in seen:
            continue
        seen.add(relative)
        targets.append(
            {
                "project_relative_path": relative,
                "purpose_zh": "本阶段生成或修改的重点产物，请优先检查。",
                "exists": str((root / relative).is_file()).lower(),
            }
        )
        if len(targets) >= 5:
            break
    return targets


def _html_link(output_dir: Path, root: Path, relative: str) -> str:
    target = Path(os.path.relpath(root / relative, output_dir)).as_posix()
    return escape(target)


def _render_html(root: Path, output_dir: Path, summary: dict[str, Any], request: dict[str, Any]) -> str:
    def list_section(title: str, items: list[Any], *, paths: bool = False) -> str:
        if not items:
            return f"<section><h2>{escape(title)}</h2><p>无。</p></section>"
        rows: list[str] = []
        for item in items:
            if paths and isinstance(item, dict) and item.get("project_relative_path"):
                relative = str(item["project_relative_path"])
                rows.append(
                    f"<li><a href=\"{_html_link(output_dir, root, relative)}\">{escape(relative)}</a>"
                    f"<br><small>{escape(str(item.get('purpose_zh') or item.get('summary_zh') or ''))}</small></li>"
                )
            else:
                rows.append(f"<li>{escape(str(item.get('summary_zh') if isinstance(item, dict) else item))}</li>")
        return f"<section><h2>{escape(title)}</h2><ul>{''.join(rows)}</ul></section>"

    manifest = summary.get("artifact_manifest") or {}
    artifact_rows = []
    for item in manifest.get("artifacts") or []:
        relative = str(item.get("project_relative_path") or "")
        link = _html_link(output_dir, root, relative) if relative else ""
        artifact_rows.append(
            "<tr>"
            f"<td><a href=\"{link}\">{escape(relative)}</a></td>"
            f"<td>{escape(str(item.get('operation') or ''))}</td>"
            f"<td>{escape(str(item.get('semantic_changed')))}</td>"
            f"<td>{escape(str(item.get('user_attention') or ''))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{escape(str(summary.get('checkpoint_title_zh') or 'Draftpaper 阶段总结'))}</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; max-width: 1100px; margin: 28px auto; padding: 0 20px; line-height: 1.6; color: #1f2937; }}
h1 {{ color: #0f172a; }} h2 {{ border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; color: #334155; }}
.meta {{ background: #f1f5f9; padding: 12px 16px; border-left: 4px solid #2563eb; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
th {{ background: #e2e8f0; }} code {{ background: #f1f5f9; padding: 2px 4px; }}
.warning {{ background: #fff7ed; border-left: 4px solid #ea580c; padding: 10px 14px; }}
</style></head>
<body>
<h1>{escape(str(summary.get('checkpoint_title_zh') or 'Draftpaper 阶段总结'))}</h1>
<div class="meta"><strong>阶段：</strong>{escape(str(summary.get('completed_stage') or ''))}<br>
<strong>状态：</strong>{escape(str(summary.get('stage_status') or ''))}<br>
<strong>摘要 hash：</strong><code>{escape(str(summary.get('stage_summary_sha256') or request.get('stage_summary_sha256') or ''))}</code></div>
{list_section('本阶段做了什么', summary.get('scientific_summary_zh') or [])}
{list_section('生成内容', summary.get('generated') or [], paths=True)}
{list_section('修改内容', summary.get('modified') or [], paths=True)}
{list_section('部署与绑定', summary.get('deployed') or [])}
{list_section('验证结果', summary.get('validated') or [])}
{list_section('失败事项', summary.get('failed') or [])}
<div class="warning">{list_section('未解决事项', summary.get('unresolved') or [])}</div>
{list_section('请重点检查', summary.get('inspection_targets') or [], paths=True)}
<section><h2>本次确认意味着什么</h2><p>{escape(str(summary.get('confirmation_meaning_zh') or ''))}</p></section>
<section><h2>拒绝或要求修改</h2><p>{escape(str(summary.get('rejection_or_refinement_route_zh') or ''))}</p></section>
<section><h2>产物明细</h2><table><thead><tr><th>路径</th><th>操作</th><th>科学语义变化</th><th>注意级别</th></tr></thead><tbody>{''.join(artifact_rows) or '<tr><td colspan="4">无已登记产物。</td></tr>'}</tbody></table></section>
<section><h2>确认命令</h2><p><code>{escape(str(request.get('confirmation_command') or ''))}</code></p></section>
</body></html>\n"""


def _publish_checkpoint_index(root: Path, report: dict[str, Any]) -> None:
    """Publish derived checkpoint pointers after the authoritative files exist."""

    stable_id = str(report.get("checkpoint_id") or "")
    if not stable_id:
        raise CheckpointSummaryError("Cannot publish a checkpoint index without checkpoint_id.")
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    index_path = root / CHECKPOINT_ROOT / "index.json"
    index_payload: dict[str, Any] = {"schema_version": "dpl.checkpoint_index.v1", "checkpoints": []}
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                index_payload = loaded
        except (OSError, ValueError):
            index_payload = {"schema_version": "dpl.checkpoint_index.v1", "checkpoints": []}
    records = [item for item in index_payload.get("checkpoints") or [] if str(item.get("checkpoint_id")) != stable_id]
    records.append(
        {
            "checkpoint_id": stable_id,
            "checkpoint_type": report.get("checkpoint_type"),
            "stage_summary_sha256": report.get("stage_summary_sha256"),
            "stage_summary_json": f"{relative_dir}/stage_summary.json",
            "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
            "created_at": report.get("created_at"),
        }
    )
    index_payload["checkpoints"] = records[-200:]
    atomic_write_json(index_path, index_payload)
    atomic_write_json(
        root / CHECKPOINT_ROOT / "latest_checkpoint.json",
        {"schema_version": "dpl.latest_checkpoint.v1", "checkpoint_id": stable_id, "stage_summary_json": f"{relative_dir}/stage_summary.json"},
    )


def write_stage_summary(
    project: str | Path,
    *,
    stage: str,
    command: str,
    payload: dict[str, Any] | None = None,
    before_artifacts: list[dict[str, Any]] | None = None,
    checkpoint_id: str | None = None,
    checkpoint_hash: str | None = None,
    publish_index: bool = True,
) -> dict[str, Any]:
    """Write the portable summary, artifact manifest, request and Chinese HTML."""

    root = project_root(project)
    data = dict(payload or {})
    explicit_paths = _payload_paths(root, data)
    current = collect_artifacts(root)
    identity_seed = {
        "stage": stage,
        "command": command,
        "artifacts": [(item.get("path"), item.get("semantic_sha256"), item.get("evidence_sha256")) for item in current if _in_stage_scope(str(item.get("path") or ""), stage)],
    }
    stable_id = checkpoint_id or f"{stage}-{_hash_payload(identity_seed)[:12]}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stable_id):
        raise CheckpointSummaryError("checkpoint_id contains unsafe path characters")
    output_dir = root / CHECKPOINT_ROOT / stable_id
    manifest = _artifact_manifest(root, stage, explicit_paths, before_artifacts)
    operations = manifest.get("artifacts") or []
    generated = [item for item in operations if item.get("operation") == "generated"]
    modified = [item for item in operations if item.get("operation") == "modified"]
    status = _decision_status(data)
    failed_values = _payload_items(data, ("errors", "error", "failure", "failure_reason"))
    if status in {"error", "failed", "blocked", "failure"} and not failed_values:
        failed_values = [f"命令返回状态：{status}"]
    unresolved_values = _payload_items(data, ("unresolved", "unresolved_issues", "pending", "pending_tasks", "missing", "warnings"))
    summary: dict[str, Any] = {
        "schema_version": CHECKPOINT_SUMMARY_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "checkpoint_title_zh": _STAGE_TITLES.get(stage, f"{stage} 阶段人工确认"),
        "completed_stage": stage,
        "command": command,
        "stage_status": "ready_for_human_review" if status not in {"error", "failed", "blocked"} else "blocked",
        "generated": generated,
        "modified": modified,
        "deployed": [_short_item(item) for item in _payload_items(data, ("deployed", "deployment", "deployment_state"))],
        "validated": ([{"summary_zh": f"{command} 返回 `{status}`，请结合下方产物检查。"}] if status in {"pass", "passed", "success", "completed", "written", "review_required", "confirmation_required", "checkpoint_created"} else []),
        "failed": [_short_item(item) for item in failed_values],
        "unresolved": [_short_item(item) for item in unresolved_values],
        "scientific_summary_zh": _scientific_summary(stage, command, data),
        "scientific_impact": [
            "本摘要只描述当前阶段的产物和状态，不把候选、fixture 或 metadata 误写成论文证据。",
            f"下游影响由当前命令 `{command}` 的状态和确认决定。",
        ],
        "inspection_targets": _inspection_targets(manifest, explicit_paths, root),
        "artifact_manifest": manifest,
        "upstream_bindings": data.get("upstream_bindings") or data.get("bindings") or {},
        "runtime_fingerprint": data.get("runtime_fingerprint"),
        "confirmation_meaning_zh": f"确认后将冻结 `{stage}` 阶段当前产物及其证据身份，并允许状态机按照该阶段的下游路线继续。确认不等于替用户判断科学结论正确。",
        "rejection_or_refinement_route_zh": "拒绝或要求修改后保留本次摘要和审计记录，先按下一步修复路线更新上游内容，再生成新的摘要和 hash；不直接覆盖本次确认版本。",
        "created_at": utc_now(),
    }
    manifest_hash = _hash_payload(manifest)
    summary["artifact_manifest_sha256"] = manifest_hash
    summary_hash = _hash_payload(summary)
    summary["stage_summary_sha256"] = summary_hash
    next_action = data.get("next_action") if isinstance(data.get("next_action"), dict) else {}
    confirmation_command = data.get("confirmation_command") or next_action.get("cli")
    refinement_command = data.get("refinement_command") or next_action.get("cli")
    request: dict[str, Any] = {
        "schema_version": CONFIRMATION_REQUEST_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "stage_summary_sha256": summary_hash,
        "checkpoint_hash": checkpoint_hash,
        "allowed_decisions": ["confirm", "refine", "reject"],
        "confirmation_command": confirmation_command,
        "refinement_command": refinement_command,
        "requires_user_decision": True,
        "created_at": utc_now(),
    }
    if not request.get("confirmation_command"):
        request["confirmation_command"] = f"python -m draftpaper_cli.cli resume --project <project> --checkpoint-hash {checkpoint_hash or summary_hash[:12]}"
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    change_report = {
        "schema_version": CHANGE_REPORT_SCHEMA,
        "checkpoint_id": stable_id,
        "checkpoint_type": stage,
        "generated": generated,
        "modified": modified,
        "deployed": summary["deployed"],
        "validated": summary["validated"],
        "failed": summary["failed"],
        "unresolved": summary["unresolved"],
        "stage_summary_sha256": summary_hash,
        "artifact_manifest_sha256": manifest_hash,
    }
    unresolved_report = {
        "schema_version": UNRESOLVED_ISSUES_SCHEMA,
        "checkpoint_id": stable_id,
        "status": "blocked" if summary["stage_status"] == "blocked" else "review_required" if summary["unresolved"] else "none",
        "issues": summary["unresolved"],
        "stage_summary_sha256": summary_hash,
    }
    agent_payload = {
        "schema_version": AGENT_PAYLOAD_SCHEMA,
        "checkpoint_id": stable_id,
        "stage": stage,
        "stage_summary_zh_html": {
            "project_relative_path": f"{relative_dir}/stage_summary.zh-CN.html",
            "absolute_path": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        },
        "stage_summary_json": str((output_dir / "stage_summary.json").resolve()),
        "artifact_manifest": str((output_dir / "artifact_manifest.json").resolve()),
        "confirmation_request": str((output_dir / "confirmation_request.json").resolve()),
        "primary_artifacts": [
            {
                "project_relative_path": str(item.get("project_relative_path") or ""),
                "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
            }
            for item in summary["inspection_targets"]
            if item.get("project_relative_path")
        ],
        "unresolved_issues": summary["unresolved"],
        "confirmation_command": request["confirmation_command"],
        "confirmation_meaning_zh": summary["confirmation_meaning_zh"],
        "stage_summary_sha256": summary_hash,
    }
    atomic_write_json(output_dir / "artifact_manifest.json", manifest)
    atomic_write_json(output_dir / "stage_summary.json", summary)
    atomic_write_json(output_dir / "confirmation_request.json", request)
    atomic_write_json(output_dir / "change_report.json", change_report)
    atomic_write_json(output_dir / "unresolved_issues.json", unresolved_report)
    atomic_write_json(output_dir / "agent_payload.json", agent_payload)
    atomic_write_text(output_dir / "stage_summary.zh-CN.html", _render_html(root, output_dir, summary, request))
    required_files = (
        output_dir / "stage_summary.json",
        output_dir / "artifact_manifest.json",
        output_dir / "confirmation_request.json",
        output_dir / "change_report.json",
        output_dir / "unresolved_issues.json",
        output_dir / "agent_payload.json",
        output_dir / "stage_summary.zh-CN.html",
    )
    if not all(path.is_file() for path in required_files):
        missing = ", ".join(str(path.name) for path in required_files if not path.is_file())
        raise CheckpointSummaryError(f"Checkpoint summary is incomplete; missing: {missing}")
    if publish_index:
        _publish_checkpoint_index(root, {**summary, "checkpoint_type": stage})
    relative_dir = (Path(CHECKPOINT_ROOT) / stable_id).as_posix()
    return {
        "checkpoint_id": stable_id,
        "stage_summary_sha256": summary_hash,
        "artifact_manifest_sha256": manifest_hash,
        "project_relative_dir": relative_dir,
        "stage_summary_json": f"{relative_dir}/stage_summary.json",
        "stage_summary_zh_html": f"{relative_dir}/stage_summary.zh-CN.html",
        "artifact_manifest": f"{relative_dir}/artifact_manifest.json",
        "confirmation_request": f"{relative_dir}/confirmation_request.json",
        "change_report": f"{relative_dir}/change_report.json",
        "unresolved_issues_report": f"{relative_dir}/unresolved_issues.json",
        "agent_payload": f"{relative_dir}/agent_payload.json",
        "absolute_stage_summary_zh_html": str((output_dir / "stage_summary.zh-CN.html").resolve()),
        "absolute_stage_summary_json": str((output_dir / "stage_summary.json").resolve()),
        "absolute_artifact_manifest": str((output_dir / "artifact_manifest.json").resolve()),
        "absolute_change_report": str((output_dir / "change_report.json").resolve()),
        "absolute_unresolved_issues": str((output_dir / "unresolved_issues.json").resolve()),
        "absolute_agent_payload": str((output_dir / "agent_payload.json").resolve()),
        "unresolved_issues": summary["unresolved"],
        "inspection_targets": summary["inspection_targets"],
        "created_at": summary["created_at"],
        "checkpoint_type": stage,
    }


def show_checkpoint_summary(project: str | Path, checkpoint_hash: str | None = None, language: str = "zh-CN") -> dict[str, Any]:
    """Read one checkpoint summary and expose exact local paths without writing state."""

    root = project_root(project)
    events = read_jsonl(root / "checkpoint_ledger.jsonl")
    selected: dict[str, Any] | None = None
    if checkpoint_hash:
        selected = next((item for item in reversed(events) if item.get("kind") == "checkpoint" and item.get("hash") == checkpoint_hash), None)
    if selected is None:
        selected = next((item for item in reversed(events) if item.get("kind") == "checkpoint"), None)
    relative = str((selected or {}).get("stage_summary_json") or "")
    if not relative:
        latest_path = root / CHECKPOINT_ROOT / "latest_checkpoint.json"
        if latest_path.is_file():
            try:
                latest = json.loads(latest_path.read_text(encoding="utf-8-sig"))
                relative = str(latest.get("stage_summary_json") or "")
            except (OSError, ValueError):
                relative = ""
    summary_path = root / relative if relative else None
    required = (
        summary_path,
        summary_path.parent / "stage_summary.zh-CN.html" if summary_path else None,
        summary_path.parent / "artifact_manifest.json" if summary_path else None,
        summary_path.parent / "confirmation_request.json" if summary_path else None,
        summary_path.parent / "change_report.json" if summary_path else None,
        summary_path.parent / "unresolved_issues.json" if summary_path else None,
        summary_path.parent / "agent_payload.json" if summary_path else None,
    )
    if not summary_path or not all(path is not None and path.is_file() for path in required):
        return {"status": "not_found", "project_path": str(root), "checkpoint_hash": checkpoint_hash, "language": language}
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    request_path = summary_path.parent / "confirmation_request.json"
    return {
        "status": "ready_for_human_review",
        "project_path": str(root),
        "checkpoint_hash": (selected or {}).get("hash") or checkpoint_hash,
        "language": language,
        "summary": summary,
        "stage_summary_zh_html": {
            "project_relative_path": summary_path.parent.joinpath("stage_summary.zh-CN.html").relative_to(root).as_posix(),
            "absolute_path": str(summary_path.parent.joinpath("stage_summary.zh-CN.html").resolve()),
            "source_semantic_sha256": summary.get("stage_summary_sha256"),
        },
        "artifact_manifest": str(summary_path.parent.joinpath("artifact_manifest.json").resolve()),
        "confirmation_request": str(request_path.resolve()),
        "change_report": str(summary_path.parent.joinpath("change_report.json").resolve()),
        "unresolved_issues_report": str(summary_path.parent.joinpath("unresolved_issues.json").resolve()),
        "agent_payload": str(summary_path.parent.joinpath("agent_payload.json").resolve()),
        "primary_artifacts": summary.get("inspection_targets") or [],
        "unresolved_issues": summary.get("unresolved") or [],
    }


def agent_artifact_paths(project: str | Path, targets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return an ASCII-safe path-only projection for CLI/Agent transport."""

    root = project_root(project)
    return [
        {
            "project_relative_path": str(item.get("project_relative_path") or ""),
            "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
        }
        for item in targets
        if item.get("project_relative_path")
    ]


def checkpoint_path_payload(project: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Build an ASCII-safe path projection for status/next-action responses."""

    root = project_root(project)
    relative_html = str(event.get("stage_summary_zh_html") or "")
    relative_json = str(event.get("stage_summary_json") or "")
    if not relative_html and relative_json:
        relative_html = str(Path(relative_json).parent / "stage_summary.zh-CN.html").replace("\\", "/")
    result: dict[str, Any] = {}
    if relative_html:
        result["stage_summary_zh_html"] = {
            "project_relative_path": relative_html.replace("\\", "/"),
            "absolute_path": str((root / relative_html).resolve()),
            "source_semantic_sha256": event.get("stage_summary_sha256"),
        }
    if relative_json:
        result["stage_summary_json"] = str((root / relative_json).resolve())
    if event.get("checkpoint_id"):
        result["checkpoint_id"] = event["checkpoint_id"]
    return result


def validate_checkpoint_summary(project: str | Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Verify that the scientific artifacts bound by a checkpoint are unchanged."""

    root = project_root(project)
    relative = str(checkpoint.get("stage_summary_json") or "")
    if not relative:
        return {"status": "legacy_unbound", "valid": True, "reasons": []}
    path = root / relative
    if not path.is_file():
        return {"status": "invalid", "valid": False, "reasons": [f"Missing checkpoint summary: {relative}"]}
    companion_files = {
        "stage_summary.zh-CN.html": path.parent / "stage_summary.zh-CN.html",
        "artifact_manifest.json": path.parent / "artifact_manifest.json",
        "confirmation_request.json": path.parent / "confirmation_request.json",
        "change_report.json": path.parent / "change_report.json",
        "unresolved_issues.json": path.parent / "unresolved_issues.json",
        "agent_payload.json": path.parent / "agent_payload.json",
    }
    missing_companions = [name for name, companion in companion_files.items() if not companion.is_file()]
    if missing_companions:
        return {"status": "invalid", "valid": False, "reasons": ["Missing checkpoint companion files: " + ", ".join(missing_companions)]}
    try:
        summary = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "valid": False, "reasons": [f"Invalid checkpoint summary: {exc}"]}
    reasons: list[str] = []
    expected_summary_hash = str(checkpoint.get("stage_summary_sha256") or summary.get("stage_summary_sha256") or "")
    if expected_summary_hash and expected_summary_hash != str(summary.get("stage_summary_sha256") or ""):
        reasons.append("Checkpoint summary hash changed.")
    recompute_payload = dict(summary)
    recompute_payload.pop("stage_summary_sha256", None)
    if str(summary.get("stage_summary_sha256") or "") != _hash_payload(recompute_payload):
        reasons.append("Checkpoint summary content does not match its semantic hash.")
    manifest = summary.get("artifact_manifest") if isinstance(summary.get("artifact_manifest"), dict) else {}
    if str(summary.get("artifact_manifest_sha256") or "") != _hash_payload(manifest):
        reasons.append("Checkpoint artifact manifest does not match its semantic hash.")
    try:
        stored_manifest = json.loads(companion_files["artifact_manifest.json"].read_text(encoding="utf-8-sig"))
        request = json.loads(companion_files["confirmation_request.json"].read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        reasons.append(f"Checkpoint companion JSON is invalid: {exc}")
    else:
        if stored_manifest != manifest:
            reasons.append("Checkpoint artifact manifest file differs from stage summary.")
        if request.get("stage_summary_sha256") != summary.get("stage_summary_sha256"):
            reasons.append("Confirmation request is not bound to the stage summary hash.")
    current = {str(item.get("path")): item for item in collect_artifacts(root) if isinstance(item, dict)}
    for item in (summary.get("artifact_manifest") or {}).get("artifacts") or []:
        relative_artifact = str(item.get("project_relative_path") or "")
        if not relative_artifact or item.get("operation") == "failed":
            continue
        current_item = current.get(relative_artifact)
        if current_item is None:
            reasons.append(f"Bound artifact is missing: {relative_artifact}")
            continue
        expected_semantic = item.get("after_semantic_sha256")
        if expected_semantic and current_item.get("semantic_sha256") != expected_semantic:
            reasons.append(f"Bound artifact semantic identity changed: {relative_artifact}")
        expected_evidence = item.get("evidence_sha256")
        if expected_evidence and current_item.get("evidence_sha256") != expected_evidence:
            reasons.append(f"Bound artifact evidence identity changed: {relative_artifact}")
    return {"status": "valid" if not reasons else "invalid", "valid": not reasons, "reasons": reasons}


def attach_checkpoint_summary(
    payload: dict[str, Any],
    *,
    project: str | Path,
    stage: str,
    command: str,
    before_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attach exact relative and absolute summary paths to an Agent payload."""

    if payload.get("stage_summary_zh_html"):
        return payload
    report = write_stage_summary(
        project,
        stage=stage,
        command=command,
        payload=payload,
        before_artifacts=before_artifacts,
        checkpoint_id=str(payload.get("checkpoint_id") or "") or None,
        checkpoint_hash=str(payload.get("checkpoint_hash") or "") or None,
    )
    result = dict(payload)
    result["stage_summary_zh_html"] = {
        "project_relative_path": report["stage_summary_zh_html"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "source_semantic_sha256": report["stage_summary_sha256"],
    }
    result["checkpoint_summary"] = {
        "checkpoint_id": report["checkpoint_id"],
        "project_relative_dir": report["project_relative_dir"],
        "absolute_path": report["absolute_stage_summary_zh_html"],
        "stage_summary_json": report["absolute_stage_summary_json"],
        "artifact_manifest": report["absolute_artifact_manifest"],
        "confirmation_request": report["confirmation_request"],
    }
    root = project_root(project)
    result["primary_artifacts"] = [
        {
            "project_relative_path": str(item.get("project_relative_path") or ""),
            "absolute_path": str((root / str(item.get("project_relative_path"))).resolve()),
        }
        for item in report["inspection_targets"]
        if item.get("project_relative_path")
    ]
    result["unresolved_issues"] = report["unresolved_issues"]
    result["stage_summary_sha256"] = report["stage_summary_sha256"]
    return result
