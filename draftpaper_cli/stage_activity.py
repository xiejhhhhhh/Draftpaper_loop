"""Evidence-backed activity bundles used by checkpoint summaries.

The bundle is intentionally deterministic and local.  It summarizes trace and
transaction receipts; it never infers Agent work from a directory listing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json
from .command_transaction import TRANSACTION_LEDGER_PATH
from .passport import collect_artifacts, project_root, read_jsonl, utc_now
from .state_kernel import atomic_write_json
from .workflow_trace import TRACE_PATH


STAGE_ACTIVITY_SCHEMA = "dpl.stage_activity_bundle.v1"

_ACTION_LABELS = {
    "read": "读取",
    "analyze": "分析",
    "generate": "生成",
    "modify": "修改",
    "reuse": "复用",
    "validate": "验证",
    "retry": "重试",
    "skip": "跳过",
    "decide": "作出审查判断",
    "rollback": "回滚",
    "external_edit": "发现外部修改",
    "command": "执行命令",
}

_STAGE_HINTS = {
    "research_plan": ("research-plan", "research_plan", "plan-project"),
    "data": ("data", "acquire", "literature"),
    "methods": ("method", "analysis", "execute"),
    "result_support": ("result-support", "result", "downgrade"),
    "core_evidence": ("core-evidence", "checkpoint", "resume"),
    "plugin": ("plugin", "skill", "capability"),
    "quality_checks": ("quality", "latex", "manuscript", "release"),
    "writing": ("write", "section", "revision", "manuscript"),
}


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def infer_stage(command: str, explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    name = str(command or "").lower()
    for stage, hints in _STAGE_HINTS.items():
        if any(hint in name for hint in hints):
            return stage
    return "state"


def _safe_path(root: Path, raw: Any) -> str | None:
    text = str(raw or "").replace("\\", "/").strip()
    if not text or "://" in text:
        return None
    candidate = Path(text)
    try:
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
        relative = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    return relative if relative and relative != "." else None


def _stage_prefixes(stage: str) -> tuple[str, ...]:
    from .checkpoint_digest import STAGE_SCOPE_PREFIXES

    return STAGE_SCOPE_PREFIXES.get(stage, (f"{stage}/", "review/"))


def _matches_stage(stage: str, command: str, row_stage: str | None) -> bool:
    if row_stage and row_stage == stage:
        return True
    if row_stage and row_stage not in {"state", ""}:
        return False
    return infer_stage(command) == stage


def _artifact_operations(
    root: Path,
    stage: str,
    before_artifacts: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    before = {str(item.get("path")): item for item in (before_artifacts or []) if item.get("path")}
    current = {str(item.get("path")): item for item in collect_artifacts(root) if item.get("path")}
    paths = sorted(
        path
        for path in set(before) | set(current)
        if any(path.startswith(prefix) for prefix in _stage_prefixes(stage))
    )
    operations: list[dict[str, Any]] = []
    for path in paths:
        old = before.get(path)
        new = current.get(path)
        old_hash = (old or {}).get("semantic_sha256") or (old or {}).get("byte_sha256") or (old or {}).get("sha256")
        new_hash = (new or {}).get("semantic_sha256") or (new or {}).get("byte_sha256") or (new or {}).get("sha256")
        if old is None:
            operation = "generated"
        elif new is None:
            operation = "deleted"
        elif old_hash == new_hash:
            operation = "reused"
        else:
            operation = "modified"
        operations.append(
            {
                "project_relative_path": path,
                "operation": operation,
                "before_semantic_sha256": (old or {}).get("semantic_sha256"),
                "after_semantic_sha256": (new or {}).get("semantic_sha256"),
                "evidence_ref": f"artifact:{path}",
            }
        )
    return operations


def _trace_action(row: dict[str, Any], *, stage: str) -> dict[str, Any]:
    command = str(row.get("command") or "unknown")
    action_kind = str(row.get("action_kind") or "command")
    output_refs = list(row.get("output_artifact_refs") or row.get("changed_paths") or [])
    input_refs = list(row.get("input_artifact_refs") or [])
    refs = [str(item) for item in [*input_refs, *output_refs] if str(item).strip()]
    if not refs:
        refs = [f"trace:{row.get('command_id') or row.get('run_id') or command}"]
    return {
        "activity_id": str(row.get("activity_id") or row.get("command_id") or _hash(row)[:16]),
        "stage": stage,
        "actor_type": str(row.get("actor_type") or "agent"),
        "actor_id": str(row.get("actor_id") or row.get("agent_session_id") or "unknown"),
        "action_kind": action_kind,
        "action_label_zh": _ACTION_LABELS.get(action_kind, action_kind),
        "command": command,
        "status": str(row.get("process_status") or row.get("transaction_status") or "unknown"),
        "attempt": int(row.get("attempt") or 1),
        "reason_codes": [str(item) for item in row.get("reason_codes") or []],
        "artifact_change_summary": row.get("artifact_change_summary") or {},
        "input_artifact_refs": input_refs,
        "output_artifact_refs": output_refs,
        "validation_result_refs": list(row.get("validation_result_refs") or []),
        "decision_refs": list(row.get("decision_refs") or []),
        "evidence_refs": refs,
        "user_visible_summary_fragment_zh": str(row.get("user_visible_summary_fragment_zh") or ""),
        "retry_of": row.get("retry_of"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
    }


def _transaction_action(row: dict[str, Any], *, stage: str) -> dict[str, Any]:
    command = str(row.get("command") or "unknown")
    status = str(row.get("transaction_status") or "unknown")
    action_kind = "rollback" if "rollback" in command else "retry" if int(row.get("attempt") or 1) > 1 else "command"
    paths = [str(item).replace("\\", "/") for item in row.get("actual_write_set") or row.get("changed_paths") or []]
    refs = [f"transaction:{row.get('command_id') or row.get('recorded_at') or command}"]
    refs.extend(f"artifact:{path}" for path in paths if path)
    return {
        "activity_id": str(row.get("command_id") or _hash(row)[:16]),
        "stage": stage,
        "actor_type": str(row.get("actor_type") or "cli"),
        "actor_id": str(row.get("actor_id") or "cli"),
        "action_kind": action_kind,
        "action_label_zh": _ACTION_LABELS.get(action_kind, action_kind),
        "command": command,
        "status": status,
        "attempt": int(row.get("attempt") or 1),
        "reason_codes": [str(row.get("failure_class"))] if row.get("failure_class") else [],
        "artifact_change_summary": {
            "created": list(row.get("created_paths") or []),
            "modified": list(row.get("modified_paths") or []),
            "deleted": list(row.get("deleted_paths") or []),
            "reused": list(row.get("reused_paths") or []),
            "skipped": list(row.get("skipped_paths") or []),
        },
        "input_artifact_refs": list(row.get("input_artifact_refs") or []),
        "output_artifact_refs": [f"artifact:{path}" for path in paths],
        "validation_result_refs": list(row.get("validation_result_refs") or []),
        "decision_refs": list(row.get("decision_refs") or []),
        "evidence_refs": refs,
        "user_visible_summary_fragment_zh": str(row.get("message") or ""),
        "retry_of": row.get("parent_command_id") if action_kind == "retry" else None,
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
    }


def _short_paths(items: Iterable[dict[str, Any]], *, limit: int = 4) -> str:
    paths = [str(item.get("project_relative_path") or "") for item in items if str(item.get("project_relative_path") or "")]
    if not paths:
        return ""
    visible = "、".join(paths[:limit])
    return visible + (f" 等 {len(paths)} 项" if len(paths) > limit else "")


def _activity_narrative(stage: str, goal: str, actions: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> str:
    """Describe recorded work without inferring scientific outcomes from files."""

    completed = [item for item in actions if str(item.get("status") or "") in {"completed", "committed", "read_only", "passed", "success"}]
    failed = [item for item in actions if str(item.get("status") or "") in {"failed", "error", "blocked", "failed_or_blocked", "not_recorded"}]
    grouped = Counter(str(item.get("action_kind") or "command") for item in completed)
    action_parts = []
    for kind in ("read", "analyze", "generate", "modify", "reuse", "validate", "retry", "skip", "decide", "rollback", "command"):
        count = grouped.get(kind, 0)
        if count:
            commands = [str(item.get("command") or "") for item in completed if str(item.get("action_kind") or "command") == kind]
            unique_commands = list(dict.fromkeys(command for command in commands if command))
            command_text = "、".join(unique_commands[:3])
            label = _ACTION_LABELS.get(kind, kind)
            action_parts.append(f"{label} {count} 项" + (f"（{command_text}）" if command_text else ""))
    generated = [item for item in artifacts if item.get("operation") == "generated"]
    modified = [item for item in artifacts if item.get("operation") == "modified"]
    reused = [item for item in artifacts if item.get("operation") == "reused"]
    deleted = [item for item in artifacts if item.get("operation") == "deleted"]
    artifact_parts = []
    for label, items in (("新生成", generated), ("修改", modified), ("复用", reused), ("删除", deleted)):
        names = _short_paths(items)
        if names:
            artifact_parts.append(f"{label}：{names}")
    clean_goal = (goal or f"完成 {stage} 阶段的既定工作").strip().rstrip("。")
    narrative = f"本阶段目标是：{clean_goal}。"
    if action_parts:
        narrative += "已记录的实际操作包括" + "；".join(action_parts) + "。"
    else:
        narrative += "未找到已提交的工作动作；页面不会把目录中的文件推断为已完成工作。"
    if artifact_parts:
        narrative += "本轮产物变化为" + "；".join(artifact_parts) + "。"
    else:
        narrative += "没有检测到相对本阶段基线的产物变化，完整成果仍在下方清单中展示。"
    output_paths = []
    for action in completed:
        for ref in action.get("output_artifact_refs") or []:
            text = str(ref)
            if text.startswith("artifact:"):
                text = text[len("artifact:") :]
            if text and text not in output_paths:
                output_paths.append(text)
    if output_paths:
        visible = "、".join(output_paths[:4])
        suffix = f" 等 {len(output_paths)} 项" if len(output_paths) > 4 else ""
        narrative += f"本次命令明确关联的输出为：{visible}{suffix}。"
    if failed:
        failure_labels = "、".join(str(item.get("command") or item.get("action_label_zh") or "未登记动作") for item in failed[:3])
        narrative += f"仍有 {len(failed)} 项未完成或需核查的活动（{failure_labels}），不会被表述为已完成。"
    else:
        narrative += "已记录活动未出现失败、阻断或缺少 receipt 的状态。"
    return narrative


def build_stage_activity_bundle(
    project: str | Path,
    *,
    stage: str,
    command: str | None = None,
    before_artifacts: Iterable[dict[str, Any]] | None = None,
    activity_rows: Iterable[dict[str, Any]] | None = None,
    stage_goal_zh: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    traces = list(activity_rows or read_jsonl(root / TRACE_PATH))
    transactions = read_jsonl(root / TRANSACTION_LEDGER_PATH)
    actions: list[dict[str, Any]] = []
    for row in traces:
        if _matches_stage(stage, str(row.get("command") or ""), row.get("stage")):
            actions.append(_trace_action(row, stage=stage))
    known_ids = {str(item.get("command_id")) for item in traces if item.get("command_id")}
    for row in transactions:
        if str(row.get("command_id") or "") in known_ids:
            continue
        if _matches_stage(stage, str(row.get("command") or ""), row.get("stage")):
            actions.append(_transaction_action(row, stage=stage))
    if command and not actions:
        actions.append(
            {
                "activity_id": f"command:{_hash({'stage': stage, 'command': command})[:16]}",
                "stage": stage,
                "actor_type": "agent",
                "actor_id": "unknown",
                "action_kind": "command",
                "action_label_zh": "执行命令",
                "command": command,
                "status": "not_recorded",
                "attempt": 1,
                "reason_codes": ["missing_trace_receipt"],
                "artifact_change_summary": {},
                "input_artifact_refs": [],
                "output_artifact_refs": [],
                "validation_result_refs": [],
                "decision_refs": [],
                "evidence_refs": [f"command:{command}"],
                "user_visible_summary_fragment_zh": "未找到该命令的完整活动 receipt，只能标记为待核查技术记录。",
                "retry_of": None,
                "started_at": None,
                "completed_at": None,
            }
        )
    actions.sort(key=lambda item: (str(item.get("started_at") or ""), str(item.get("activity_id") or "")))
    artifacts = _artifact_operations(root, stage, before_artifacts)
    counts = Counter(str(item.get("action_kind") or "command") for item in actions)
    statuses = Counter(str(item.get("status") or "unknown") for item in actions)
    generated = [item for item in artifacts if item.get("operation") == "generated"]
    modified = [item for item in artifacts if item.get("operation") == "modified"]
    reused = [item for item in artifacts if item.get("operation") == "reused"]
    failed = [item for item in actions if str(item.get("status")) in {"failed", "error", "blocked", "failed_or_blocked"}]
    stage_goal = str(stage_goal_zh or f"完成 {stage} 阶段的既定工作并保留可审计证据。")
    sentence = _activity_narrative(stage, stage_goal, actions, artifacts)
    bundle = {
        "schema_version": STAGE_ACTIVITY_SCHEMA,
        "bundle_id": f"activity-{_hash({'stage': stage, 'actions': actions, 'artifacts': artifacts})[:16]}",
        "project_id": _project_id(root),
        "stage": stage,
        "command": command,
        "stage_goal_zh": stage_goal,
        "narrative_zh": sentence,
        "actions": actions,
        "artifact_changes": artifacts,
        "action_counts": dict(sorted(counts.items())),
        "status_counts": dict(sorted(statuses.items())),
        "generated": generated,
        "modified": modified,
        "reused": reused,
        "failed": failed,
        "unresolved": [item for item in actions if str(item.get("status")) in {"not_recorded", "blocked", "failed", "error", "failed_or_blocked"}],
        "coverage": {
            "activity_count": len(actions),
            "activity_with_evidence_refs": sum(bool(item.get("evidence_refs")) for item in actions),
            "committed_action_count": sum(str(item.get("status") or "") in {"completed", "committed", "read_only", "passed", "success"} for item in actions),
            "artifact_count": len(artifacts),
            "artifact_paths_with_identity": sum(bool(item.get("after_semantic_sha256") or item.get("before_semantic_sha256")) for item in artifacts),
        },
        "created_at": utc_now(),
    }
    bundle["bundle_sha256"] = _hash(bundle)
    return bundle


def write_stage_activity_bundle(
    project: str | Path,
    output_dir: str | Path,
    *,
    stage: str,
    command: str | None = None,
    before_artifacts: Iterable[dict[str, Any]] | None = None,
    stage_goal_zh: str | None = None,
) -> dict[str, Any]:
    bundle = build_stage_activity_bundle(project, stage=stage, command=command, before_artifacts=before_artifacts, stage_goal_zh=stage_goal_zh)
    path = Path(output_dir) / "stage_activity_bundle.json"
    atomic_write_json(path, bundle)
    return {"bundle": bundle, "path": str(path.resolve())}


def show_stage_activity(project: str | Path, *, stage: str) -> dict[str, Any]:
    bundle = build_stage_activity_bundle(project, stage=stage)
    return {"status": "passed", "project_path": str(project_root(project)), "stage": stage, "bundle": bundle}


def _project_id(project: Path) -> str | None:
    try:
        payload = json.loads((project / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = [
    "STAGE_ACTIVITY_SCHEMA",
    "build_stage_activity_bundle",
    "infer_stage",
    "show_stage_activity",
    "write_stage_activity_bundle",
]
