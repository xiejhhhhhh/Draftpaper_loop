"""Build one human-review packet for literature retention and evidence choices."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project


PACKET_JSON = "literature_confirmation_packet.json"
PACKET_MARKDOWN = "literature_confirmation_packet.zh-CN.md"
TASKS_JSON = "unresolved_reference_tasks.json"


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _source_types(item: dict[str, Any]) -> list[str]:
    values = {str(item.get("source_type") or "").strip()}
    values.update(
        str(record.get("source_type") or "").strip()
        for record in item.get("source_records") or []
        if isinstance(record, dict)
    )
    return sorted(value for value in values if value)


def build_literature_confirmation_packet(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    references = state.path / "references"
    items_payload = _read_json(references / "literature_items.json", [])
    items = items_payload.get("items", []) if isinstance(items_payload, dict) else items_payload
    items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    rejection = _read_json(references / "literature_rejection_report.json", {})
    coverage = _read_json(references / "literature_coverage.json", {})
    provider = _read_json(references / "literature_provider_report.json", {})
    unresolved_bindings = _read_json(references / "unresolved_document_bindings.json", {"items": []})
    role_gaps = [str(value) for value in coverage.get("gaps") or []]
    rejected = [value for value in rejection.get("rejections") or [] if isinstance(value, dict)]
    routes = Counter()
    source_counts = Counter()
    for item in items:
        for source in _source_types(item):
            source_counts[source] += 1
        for receipt in item.get("document_parses") or []:
            if isinstance(receipt, dict):
                routes[str(receipt.get("route") or receipt.get("parser") or "unknown")] += 1
    candidates = []
    for index, item in enumerate(items, start=1):
        candidates.append({
            "candidate_id": f"ref-{index:04d}",
            "citation_key": item.get("bibtex_key", ""),
            "title": item.get("title", ""),
            "source_types": _source_types(item),
            "reference_origin": item.get("reference_origin") or "external_search",
            "candidate_state": item.get("candidate_state") or "unknown",
            "retained": bool(item.get("retained")),
            "role_evidence": item.get("role_evidence") or {},
            "evidence_passage_count": len(item.get("evidence_passages") or []),
            "parser_routes": sorted({
                str(receipt.get("route") or receipt.get("parser") or "unknown")
                for receipt in item.get("document_parses") or []
                if isinstance(receipt, dict)
            }),
        })
    unresolved_tasks = []
    for role in role_gaps:
        unresolved_tasks.append({
            "task_id": f"literature-role-gap:{role}",
            "kind": "role_gap",
            "role": role,
            "blocking": False,
            "action": "confirm_gap_or_add_a_source",
        })
    for item in rejected:
        unresolved_tasks.append({
            "task_id": f"literature-candidate:{item.get('title', '')}",
            "kind": "rejected_candidate",
            "title": item.get("title", ""),
            "rejection_codes": item.get("rejection_codes") or [],
            "blocking": False,
            "action": "retain_only_if_user_can_supply_topic_evidence",
        })
    unresolved_tasks.extend({
        "task_id": f"document-binding:{index}",
        "kind": "unresolved_document_binding",
        "blocking": False,
        "action": "select_matching_reference_or_leave_unbound",
    } for index, _ in enumerate(unresolved_bindings.get("items") or [], start=1))
    packet = {
        "schema_version": "dpl.literature_confirmation_packet.v1",
        "status": "ready_for_human_confirmation",
        "project_id": state.metadata.get("project_id"),
        "project_path": "<project>",
        "query_contract": _read_json(references / "query_contract.json", {}),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejected_candidate_count": len(rejected),
        "source_counts": dict(sorted(source_counts.items())),
        "parser_route_counts": dict(sorted(routes.items())),
        "role_gaps": role_gaps,
        "provider_status": provider,
        "unresolved_task_count": len(unresolved_tasks),
        "review_decisions": {
            "retain_or_exclude_candidates": "human_required",
            "role_assignments": "human_required_for_ambiguous_items",
            "literature_gaps": "accept_gap_or_add_source",
            "parser_upgrade": "accept_or_decline_for_complex_pdf",
        },
        "policy": {
            "does_not_auto_cite": True,
            "curated_sources_preserved": True,
            "online_provider_success_is_not_relevance": True,
            "remote_parser_requires_project_consent": True,
        },
    }
    _write_json(references / PACKET_JSON, packet)
    _write_json(references / TASKS_JSON, {
        "schema_version": "dpl.unresolved_reference_tasks.v1",
        "status": "review_required" if unresolved_tasks else "none",
        "tasks": unresolved_tasks,
    })
    lines = [
        "# 文献人工确认包",
        "",
        "> 这是文献进入研究蓝图前的集中确认材料。该文件不会自动修改文献保留状态，也不会自动把 PDF 中的参考文献加入正文。",
        "",
        f"- 状态：**{packet['status']}**",
        f"- 候选文献：**{len(candidates)}**",
        f"- 被相关性门禁拒绝：**{len(rejected)}**",
        f"- 待处理任务：**{len(unresolved_tasks)}**",
        "",
        "## 来源与解析器",
        "",
        "| 来源或解析器 | 数量 |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(source_counts.items()))
    lines.extend(f"| parser:`{key}` | {value} |" for key, value in sorted(routes.items()))
    lines.extend(["", "## 用户需要一次性确认的内容", "", "1. 保留、排除或暂缓候选文献。", "2. 有歧义文献的写作角色：研究空白、数据来源、方法、评估标准、基线或局限性。", "3. 检索缺口是否接受为真实缺口，还是补充 Zotero、本地 PDF 或新的在线检索。", "4. 复杂 PDF 是否允许在合规且满足限制时调用 MinerU Agent，或改用用户自己的 endpoint。", ""])
    if role_gaps:
        lines.extend(["## 当前文献角色缺口", "", *[f"- `{role}`：需要补充来源或由用户确认保留缺口。" for role in role_gaps], ""])
    if rejected:
        lines.extend(["## 相关性门禁拒绝的候选", "", *[f"- {item.get('title', '')}：{', '.join(item.get('rejection_codes') or []) or '未通过相关性门禁'}" for item in rejected], ""])
    lines.extend(["## 边界", "", "- Zotero、本地导入和用户手工保留项不会因外部排序被静默删除。", "- 在线 provider 返回成功不等于文献与当前研究主题相关。", "- 解析器产生的 bibliography candidate 需要身份、元数据和引用证据核查后才能进入正文。", ""])
    (references / PACKET_MARKDOWN).write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": packet["status"],
        "project_path": str(state.path),
        "packet": f"references/{PACKET_JSON}",
        "markdown": f"references/{PACKET_MARKDOWN}",
        "tasks": f"references/{TASKS_JSON}",
        "candidate_count": len(candidates),
        "unresolved_task_count": len(unresolved_tasks),
    }
