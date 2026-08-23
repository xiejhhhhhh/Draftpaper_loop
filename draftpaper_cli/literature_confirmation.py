"""Build one human-review packet for literature retention and evidence choices."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .literature_teaching_corpus import (
    build_literature_teaching_corpus,
    literature_confirmation_binding,
    literature_confirmation_packet_hash,
    write_literature_teaching_corpus,
)
from .project_scaffold import _write_json, utc_now
from .project_state import load_project

PACKET_JSON = "literature_confirmation_packet.json"
PACKET_MARKDOWN = "literature_confirmation_packet.zh-CN.md"
RECEIPT_JSON = "literature_confirmation_receipt.json"
TASKS_JSON = "unresolved_reference_tasks.json"


class LiteratureConfirmationError(RuntimeError):
    """Raised when a user confirmation is not bound to the current review packet."""


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
    teaching_candidate = build_literature_teaching_corpus(state.path)
    accepted_corpus_candidates = [
        item
        for item in teaching_candidate.get("accepted_works") or ()
        if isinstance(item, dict)
    ]
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
        "confirmed_corpus_candidate_count": len(accepted_corpus_candidates),
        "confirmed_corpus_candidates": [
            {
                "canonical_work_id": item.get("canonical_work_id"),
                "citation_key": item.get("citation_key"),
                "title": item.get("title"),
                "citation_eligibility": item.get("citation_eligibility"),
                "role_bindings": item.get("role_bindings") or [],
                "current_project_use": item.get("current_project_use"),
            }
            for item in accepted_corpus_candidates
        ],
        "confirmed_corpus_integrity": teaching_candidate.get("set_integrity") or {},
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
    packet["confirmation_binding"] = literature_confirmation_binding(state.path)
    packet["packet_hash"] = literature_confirmation_packet_hash(packet)
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
        f"- 确认哈希：`{packet['packet_hash']}`",
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
    lines.extend(
        [
            "## 将进入正式教学语料的文献集合",
            "",
            "以下集合由 canonical registry、active literature snapshot 与 reference usage plan 的交集构成。"
            + "确认 receipt 后，Draftpaper_learn 只允许这些 work 进入正式阅读顺序和深读任务。",
            "",
        ]
    )
    if accepted_corpus_candidates:
        for item in accepted_corpus_candidates:
            roles = ", ".join(
                str(binding.get("citation_role") or "")
                for binding in item.get("role_bindings") or []
                if isinstance(binding, dict) and str(binding.get("citation_role") or "")
            )
            lines.append(
                f"- `{item.get('citation_key') or ''}` · {item.get('title') or ''}"
                f" · role: `{roles or 'unclassified'}`"
            )
    else:
        lines.append("- 当前三个 Core 合同没有形成可确认的交集；先修复 registry、active snapshot 或 usage plan。")
    lines.append("")
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
        "confirmed_corpus_candidate_count": len(accepted_corpus_candidates),
        "unresolved_task_count": len(unresolved_tasks),
        "packet_hash": packet["packet_hash"],
    }


def confirm_literature_corpus(project: str | Path, *, packet_hash: str) -> dict[str, Any]:
    """Write a human-confirmation receipt for one exact literature corpus.

    This command deliberately does not modify the accepted records themselves:
    it only records that the user accepted the current registry, active
    snapshot and usage-plan intersection after inspecting its review packet.
    Any later change to one of those artifacts invalidates the receipt.
    """

    state = load_project(project)
    references = state.path / "references"
    packet_path = references / PACKET_JSON
    packet = _read_json(packet_path, {})
    if not packet_path.is_file() or not isinstance(packet, dict):
        raise LiteratureConfirmationError("Run review-literature-coverage before confirming a literature corpus.")
    expected_hash = literature_confirmation_packet_hash(packet)
    if str(packet.get("packet_hash") or "") != expected_hash:
        raise LiteratureConfirmationError("The literature review packet is malformed or was edited outside its hash-bound review flow.")
    if packet_hash != expected_hash:
        raise LiteratureConfirmationError("The supplied packet hash does not match the current literature review packet.")
    current_binding = literature_confirmation_binding(state.path)
    if packet.get("confirmation_binding") != current_binding:
        raise LiteratureConfirmationError("The literature corpus changed after review; regenerate the packet and confirm the new hash.")
    if not current_binding.get("accepted_citation_keys"):
        raise LiteratureConfirmationError("The current literature packet contains no accepted canonical works to confirm.")
    if current_binding.get("accepted_citation_keys") != current_binding.get("registry_citation_keys"):
        raise LiteratureConfirmationError(
            "The canonical registry, active literature snapshot and usage plan do not yet agree; resolve the missing bindings before confirmation."
        )
    receipt = {
        "schema_version": "dpl.literature_confirmation_receipt.v1",
        "status": "confirmed",
        "decision": "accepted",
        "confirmed_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "confirmation_packet": f"references/{PACKET_JSON}",
        "confirmation_packet_hash": expected_hash,
        "confirmation_binding": current_binding,
        "decision_boundary": "The user confirmed this exact literature corpus for teaching and project-role use; rejected, quarantined and unbound records remain excluded.",
    }
    _write_json(references / RECEIPT_JSON, receipt)
    corpus = write_literature_teaching_corpus(state.path)
    if str(corpus.get("corpus_status") or "") != "confirmed":
        raise LiteratureConfirmationError(
            "The confirmation receipt was written but the canonical literature contracts no longer agree; review the regenerated packet before publication."
        )
    return {
        "status": "confirmed",
        "project_path": str(state.path),
        "packet_hash": expected_hash,
        "receipt": f"references/{RECEIPT_JSON}",
        "corpus_manifest": "references/literature_teaching_corpus_manifest.json",
        "corpus_snapshot_hash": corpus["corpus_snapshot_hash"],
        "accepted_work_count": len(current_binding["accepted_citation_keys"]),
        "next_command": f'python -m draftpaper_cli.cli rebuild-literature-index --project "{state.path}"',
    }
