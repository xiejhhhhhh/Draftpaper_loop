"""Offline HTML rendering for human checkpoint summaries."""

from __future__ import annotations

import os
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Any

from .checkpoint_fingerprint import human_scientific_delta_summary, scientific_delta_field_label


_STATE_LABELS = {
    "confirmable": "可以确认",
    "stale": "证据已过期",
    "blocked": "存在阻断问题",
    "preview_only": "仅预览，不可确认",
}

_STATE_LABELS_EN = {
    "confirmable": "Ready for confirmation",
    "stale": "Evidence is stale",
    "blocked": "Blocking issue present",
    "preview_only": "Preview only",
    "legacy_unqualified": "Legacy package",
}


def _link(root: Path, output_dir: Path, relative: str) -> str:
    candidate = Path(relative.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return ""
    target = root / candidate
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        return ""
    return escape(Path(os.path.relpath(target, output_dir)).as_posix())


def _text(value: Any) -> str:
    return escape(str(value or ""))


def _status(value: Any) -> str:
    normalized = str(value or "unknown").lower()
    if normalized in {"pass", "passed", "success", "supported", "written", "completed", "true"}:
        return "通过"
    if normalized in {"conditional_pass", "conditional", "warning"}:
        return "条件通过"
    if normalized in {"fail", "failed", "missing", "blocked", "stale"}:
        return "阻断"
    return str(value or "未登记")


def _simple_list(title: str, items: list[Any], *, class_name: str = "") -> str:
    if not items:
        return f'<section class="section {class_name}"><h2>{_text(title)}</h2><p class="muted">无。</p></section>'
    rows = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("summary_zh") or item.get("detail_zh") or item.get("name_zh") or item.get("title_zh") or ""
        else:
            value = item
        rows.append(f"<li>{_text(value)}</li>")
    return f'<section class="section {class_name}"><h2>{_text(title)}</h2><ul>{"".join(rows)}</ul></section>'


def _render_table_preview(item: dict[str, Any]) -> str:
    preview = item.get("preview") or {}
    columns = [str(column) for column in preview.get("columns") or []]
    rows = preview.get("rows") or []
    if not columns or not rows:
        return ""
    header = "".join(f"<th>{_text(column)}</th>" for column in columns)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{_text(row.get(column))}</td>" for column in columns) + "</tr>")
    return (
        '<div class="preview-table"><table><thead><tr>'
        + header
        + "</tr></thead><tbody>"
        + "".join(body)
        + '</tbody></table><small class="muted">仅显示有限行预览，完整文件请打开原始路径。</small></div>'
    )


def _render_figure_context(item: dict[str, Any]) -> str:
    """Render concise figure metadata without embedding scientific claims."""

    parts = []
    caption = str(item.get("caption") or "")
    if caption:
        parts.append(f'<p><strong>图表说明：</strong>{_text(caption)}</p>')
    statistics = item.get("statistics") or {}
    if isinstance(statistics, dict) and statistics:
        rows = []
        for key, value in list(statistics.items())[:8]:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            rows.append(f"<li><code>{_text(key)}</code>：{_text(value)}</li>")
        parts.append('<div class="subline"><strong>图表关键统计：</strong></div><ul>' + "".join(rows) + "</ul>")
    return "".join(parts)


def _render_item(root: Path, output_dir: Path, item: dict[str, Any]) -> str:
    relative = str(item.get("project_relative_path") or "")
    href = _link(root, output_dir, relative)
    title = item.get("title_zh") or relative
    preview = item.get("preview") or {}
    image_path = str(preview.get("image_path") or "")
    image_href = _link(root, output_dir, image_path) if image_path else ""
    image_html = f'<img class="figure-preview" src="{image_href}" alt="{_text(title)}">' if image_href else ""
    code_files = item.get("code_files") or []
    code_html = ""
    if code_files:
        code_links = [
            f'<a href="{_link(root, output_dir, str(code))}">{_text(code)}</a>'
            for code in code_files
            if _link(root, output_dir, str(code))
        ]
        code_html = f'<div class="subline"><strong>生成代码：</strong>{"、".join(code_links)}</div>'
    hash_html = '<small class="hash">' + _text(item.get("after_byte_sha256") or item.get("sha256") or "未登记 hash") + "</small>"
    return (
        '<article class="artifact-item">'
        f"{image_html}<div class=\"artifact-body\"><h4>{_text(title)}</h4>"
        f'<div class="path"><a href="{href}">{_text(relative)}</a></div>'
        f'{_render_figure_context(item) if item.get("deliverable_group") == "figure" else ""}'
        f'<p>{_text(item.get("scientific_relevance_zh") or item.get("purpose_zh"))}</p>'
        f'<div class="subline"><strong>操作：</strong>{_text(item.get("operation"))}　<strong>审阅级别：</strong>{_text(item.get("review_priority"))}</div>'
        f'{code_html}{_render_table_preview(item)}{hash_html}</div></article>'
    )


def _render_groups(root: Path, output_dir: Path, groups: list[dict[str, Any]]) -> str:
    sections = []
    for group in groups:
        items = group.get("items") or []
        body = "".join(_render_item(root, output_dir, item) for item in items if isinstance(item, dict))
        technical = group.get("group_id") in {"manifest", "run_evidence"}
        wrapper = f"<details {'open' if not technical else ''}><summary>{_text(group.get('title_zh'))}（{len(items)} 项）</summary>{body}</details>"
        sections.append(f'<section class="deliverable-group">{wrapper}</section>')
    return "".join(sections) or '<p class="muted">未登记阶段成果。</p>'


def _render_changes(root: Path, output_dir: Path, changes: dict[str, list[dict[str, Any]]]) -> str:
    labels = (("generated", "新增"), ("modified", "修改"), ("deployed", "部署/绑定"), ("failed", "失败"), ("unchanged", "未变化但属于确认范围"))
    rows = []
    for key, label in labels:
        items = changes.get(key) or []
        if not items:
            continue
        for item in items[:80]:
            relative = str(item.get("project_relative_path") or "")
            rows.append(
                f'<tr><td>{_text(label)}</td><td><a href="{_link(root, output_dir, relative)}">{_text(relative)}</a></td>'
                f'<td>{_text(item.get("deliverable_group"))}</td><td>{_text(item.get("after_byte_sha256") or "")}</td></tr>'
            )
    if not rows:
        return '<p class="muted">没有相对上一快照登记的变化，但完整成果仍在上方展示。</p>'
    return '<table><thead><tr><th>变化类型</th><th>路径</th><th>分组</th><th>after hash</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _render_validation(root: Path, output_dir: Path, checks: list[dict[str, Any]]) -> str:
    rows = []
    for item in checks:
        evidence = str(item.get("evidence") or "")
        link = _link(root, output_dir, evidence) if evidence else ""
        evidence_html = f'<a href="{link}">{_text(evidence)}</a>' if link else _text(evidence)
        rows.append(
            f'<tr><td>{_text(item.get("name_zh"))}</td><td><span class="status status-{str(item.get("status") or "unknown").lower()}">{_text(_status(item.get("status")))}</span></td>'
            f'<td>{_text(item.get("detail_zh"))}</td><td>{evidence_html}</td><td>{"是" if item.get("blocking") else "否"}</td></tr>'
        )
    return '<table><thead><tr><th>验证项</th><th>状态</th><th>结论</th><th>证据</th><th>阻断</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>" if rows else '<p class="muted">未登记验证。</p>'


def _render_evidence_identity(summary: dict[str, Any]) -> str:
    """Show the identity that makes a metric or denominator reviewable."""

    metrics = dict(summary.get("core_metrics") or {})
    metrics["sample_flow"] = summary.get("sample_flow") or metrics.get("sample_flow") or []
    fields = (
        ("metric_definition_id", metrics.get("metric") or ""),
        ("task_id", metrics.get("task_id") or ""),
        ("cohort_id", metrics.get("cohort_id") or ""),
        ("sample_unit", metrics.get("sample_unit") or ""),
        ("model_id", metrics.get("model_id") or ""),
        ("validation_design_id", metrics.get("validation_design") or ""),
        ("split_id", metrics.get("split_id") or ""),
        ("aggregation_id", metrics.get("aggregation_id") or ""),
        ("metric_identity_status", metrics.get("metric_identity_status") or "未登记"),
    )
    rows = "".join(f"<tr><th>{_text(key)}</th><td>{_text(value) or '未登记'}</td></tr>" for key, value in fields)
    counts = metrics.get("sample_flow") or metrics.get("count_evidence") or []
    count_rows = []
    for item in counts:
        if not isinstance(item, dict):
            continue
        count_rows.append(
            "<tr>"
            f"<td>{_text(item.get('count_definition_id'))}</td>"
            f"<td>{_text(item.get('entity_type'))}</td>"
            f"<td>{_text(item.get('count_mode'))}</td>"
            f"<td>{_text(item.get('cohort_id'))}</td>"
            f"<td>{_text(item.get('filter_contract_id')) or '未登记'}</td>"
            f"<td>{_text(item.get('value'))}</td>"
            f"<td>{'完整' if item.get('identity_complete') else '缺身份'}</td>"
            "</tr>"
        )
    count_html = (
        "<table><thead><tr><th>计数定义</th><th>实体类型</th><th>计数方式</th><th>cohort</th><th>筛选合同</th><th>数值</th><th>身份</th></tr></thead>"
        f"<tbody>{''.join(count_rows)}</tbody></table>"
        if count_rows
        else '<p class="muted">尚未登记 typed CountEvidence；裸 source_rows 不能作为确认依据。</p>'
    )
    return (
        '<section class="section"><h2>证据身份与样本分母</h2>'
        '<p class="muted">先确认指标、模型、验证设计和分母身份，再判断数值是否一致。不同身份的数值不会被自动合并。</p>'
        f'<div class="two-col"><div><table><tbody>{rows}</tbody></table></div><div><p><strong>样本流程</strong></p>{count_html}</div></div></section>'
    )


def _render_decision_routes(routes: list[dict[str, Any]]) -> str:
    """Render human route choices without treating either route as selected."""

    if not routes:
        return ""
    cards = []
    for route in routes:
        label = route.get("label") or route.get("route") or "未命名路线"
        description = route.get("description") or "未登记路线说明。"
        stale_policy = route.get("stale_policy") or "未登记下游影响范围。"
        command = route.get("current_executable_command") or "等待用户选择后生成。"
        cards.append(
            '<article class="route-card">'
            f"<h3>{_text(label)}</h3>"
            f"<p>{_text(description)}</p>"
            f"<p><strong>下游影响：</strong>{_text(stale_policy)}</p>"
            f"<p><strong>选择后执行：</strong><code>{_text(command)}</code></p>"
            "</article>"
        )
    return '<section class="section route-section"><h2>人工决策路线</h2><p class="muted">以下路线互斥；页面只展示选项，不代表系统已替用户选择。</p>' + "".join(cards) + "</section>"


def _render_selected_route(state: dict[str, Any]) -> str:
    if str(state.get("status") or "") != "selected":
        return ""
    label = state.get("selected_label") or state.get("selected_route") or "已登记路线"
    commands = [str(item) for item in state.get("next_commands") or [] if item]
    command_html = "".join(f"<li><code>{_text(command)}</code></li>" for command in commands)
    if not command_html:
        command_html = '<li class="muted">尚未登记下一条可执行命令。</li>'
    return (
        '<section class="section route-section"><h2>已选择的人工路线</h2>'
        f"<p><strong>{_text(label)}</strong> 已记录。页面不会重新要求选择，但在该路线任务完成前仍不能确认结果。</p>"
        f"<p><strong>下一步任务：</strong></p><ul>{command_html}</ul></section>"
    )


def _render_activity(summary: dict[str, Any]) -> str:
    """Render recorded Agent/CLI actions before the complete artifact list."""

    activity = summary.get("stage_activity_bundle") if isinstance(summary.get("stage_activity_bundle"), dict) else {}
    actions = activity.get("actions") or []
    if not actions:
        return '<section class="section warning"><h2>Agent实际工作</h2><p>未找到可追溯的活动或事务 receipt；不能仅凭目录产物推断本阶段做了什么。</p></section>'
    rows = []
    for item in actions[:120]:
        evidence = ", ".join(str(ref) for ref in item.get("evidence_refs") or [])
        fragment = str(item.get("user_visible_summary_fragment_zh") or "")
        rows.append(
            f'<tr><td>{_text(item.get("action_label_zh") or item.get("action_kind"))}</td>'
            f'<td>{_text(item.get("actor_type"))} / {_text(item.get("actor_id"))}</td>'
            f'<td>{_text(item.get("command"))}</td><td>{_text(item.get("status"))}</td>'
            f'<td>{_text(fragment or evidence)}</td></tr>'
        )
    coverage = activity.get("coverage") or {}
    return (
        '<section class="section activity"><h2>Agent实际工作与本阶段总结</h2>'
        f'<p class="narrative">{_text(activity.get("narrative_zh") or summary.get("activity_summary_zh"))}</p>'
        f'<p class="muted">活动 {coverage.get("activity_count", len(actions))} 项，其中 '
        f'{coverage.get("activity_with_evidence_refs", 0)} 项有证据引用；每一行均来自 workflow trace 或 transaction receipt。</p>'
        '<div class="preview-table"><table><thead><tr><th>动作</th><th>主体</th><th>命令</th><th>结果</th><th>实际内容/证据引用</th></tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table></div></section>'
    )


def _render_baseline_refs(summary: dict[str, Any], output_dir: Path) -> str:
    refs = summary.get("baseline_refs") if isinstance(summary.get("baseline_refs"), dict) else {}
    requirement = summary.get("review_requirement") or "human_required"
    decision = summary.get("decision_status") or "pending"
    actor = summary.get("decision_actor_type") or "none"
    rows = "".join(f"<tr><th>{_text(key)}</th><td><code>{_text(value or '未登记')}</code></td></tr>" for key, value in refs.items())
    candidate_hash = str(summary.get("revision_candidate_sha256") or "")
    candidate_html = (
        f'<p><strong>本次修订候选包 SHA-256：</strong><code>{_text(candidate_hash)}</code></p>'
        if candidate_hash
        else ""
    )
    receipt_path = output_dir / "review_decision_receipt.json"
    receipt_html = ""
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            receipt = {}
        if isinstance(receipt, dict):
            receipt_html = (
                f'<p><strong>最近一次审查 receipt：</strong>{_text(receipt.get("decision_status"))}；'
                f'主体 {_text(receipt.get("actor_type"))}/{_text(receipt.get("actor_id"))}；'
                f'<code>{_text(receipt.get("receipt_sha256"))}</code></p>'
            )
    return (
        '<section class="section"><h2>审查主体、自动继续与纵向基线</h2>'
        f'<p><strong>审查要求：</strong>{_text(requirement)}　<strong>决策状态：</strong>{_text(decision)}　<strong>决策主体：</strong>{_text(actor)}</p>'
        + candidate_html
        + receipt_html
        + (f'<table><tbody>{rows}</tbody></table>' if rows else '<p class="muted">当前尚未绑定科学基线；这是首轮或旧项目迁移状态。</p>')
        + '</section>'
    )


def render_checkpoint_audit_html(root: Path, output_dir: Path, summary: dict[str, Any], request: dict[str, Any]) -> str:
    """Render the complete technical audit companion for a checkpoint."""

    review_state = str(summary.get("review_state") or "confirmable")
    state_label = _STATE_LABELS.get(review_state, review_state)
    identity = summary.get("identity") or {}
    counts = summary.get("deliverable_counts") or {}
    metrics = summary.get("core_metrics") or {}
    confirmable = review_state == "confirmable" and bool(summary.get("stage_status") != "blocked")
    confirmation = summary.get("confirmation") or {}
    if not confirmation:
        confirmation = {
            "confirmable": confirmable,
            "meaning_zh": summary.get("confirmation_meaning_zh") or "确认后冻结本阶段证据身份并允许下游继续。",
            "command": request.get("confirmation_command"),
            "refinement_route_zh": summary.get("rejection_or_refinement_route_zh") or "拒绝后重新打开受影响的上游阶段。",
        }
    confirmation_allowed = bool((summary.get("confirmation_contract") or {}).get("confirmation_command_allowed", confirmable))
    confirmation_command = confirmation.get("command") if confirmable and confirmation_allowed else None
    requirement = str(summary.get("review_requirement") or "human_required")
    warning = "" if confirmation_allowed else '<p class="blocking-note">当前页面用于审阅和提醒，不能直接确认。请先处理阻断问题，或按页面显示的 Agent 委托/人工决策路径继续。</p>'
    if requirement == "notify_only":
        warning = '<p class="testing-note">本阶段为通知型审查：系统已记录摘要并自动继续，仍保留完整产物和审计路径供复核。</p>'
    test_note = (
        '<p class="testing-note">当前为匿名 fixture 测试模式：测试流程跳过人工确认动作；这不代表任何真实科研结果已被用户确认。</p>'
        if summary.get("test_auto_confirmation")
        else ""
    )
    artifact_manifest_link = _link(root, output_dir, str(summary.get("artifact_manifest_path") or ""))
    summary_json_link = _link(root, output_dir, str(summary.get("stage_summary_path") or ""))
    metric_text = ""
    if metrics.get("run_id"):
        metric_text = f"运行 {metrics.get('run_id')} · {metrics.get('validation_design') or '验证设计未登记'} · 样本单位 {metrics.get('sample_unit') or '未登记'}"
    stats = [
        ("图表", counts.get("figure", 0)),
        ("表格", counts.get("table", 0)),
        ("代码", counts.get("code", 0)),
        ("报告/证据", counts.get("prose", 0) + counts.get("review_report", 0) + counts.get("run_evidence", 0)),
        ("未解决", len(summary.get("unresolved") or [])),
    ]
    stat_html = "".join(f'<div class="stat"><strong>{_text(value)}</strong><span>{_text(label)}</span></div>' for label, value in stats)
    key_findings = _simple_list("关键发现", summary.get("key_findings") or [])
    decision_routes = _render_decision_routes(summary.get("decision_routes") or [])
    selected_route = _render_selected_route(summary.get("decision_route_state") or {})
    boundaries = _simple_list("论断边界", summary.get("claim_boundaries") or [], class_name="boundary")
    unresolved = _simple_list("未解决事项", summary.get("unresolved") or [], class_name="warning")
    activity_html = _render_activity(summary)
    baseline_html = _render_baseline_refs(summary, output_dir)
    primary = summary.get("inspection_targets") or []
    primary_rows = []
    for item in primary:
        relative = str(item.get("project_relative_path") or "")
        primary_rows.append(f'<li><a href="{_link(root, output_dir, relative)}">{_text(relative)}</a><small>{_text(item.get("purpose_zh"))}</small></li>')
    primary_html = "<ul>" + "".join(primary_rows) + "</ul>" if primary_rows else '<p class="muted">暂无重点文件。</p>'
    manifest_html = f'<a href="{artifact_manifest_link}">artifact_manifest.json</a>' if artifact_manifest_link else "未登记"
    json_html = f'<a href="{summary_json_link}">stage_summary.json</a>' if summary_json_link else "未登记"
    command_html = f'<code>{_text(confirmation_command)}</code>' if confirmation_command else '<span class="muted">当前无可执行确认命令。</span>'
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_text(summary.get("checkpoint_title_zh") or "Draftpaper 阶段成果审阅")}</title>
<style>
:root {{ color-scheme: light; --ink:#172033; --muted:#5b6678; --line:#d9e0ea; --blue:#1d4ed8; --blue-soft:#eff6ff; --green:#15803d; --green-soft:#f0fdf4; --orange:#c2410c; --orange-soft:#fff7ed; --red:#b91c1c; --red-soft:#fef2f2; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f8fafc; color:var(--ink); font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif; line-height:1.62; }}
main {{ max-width:1280px; margin:0 auto; padding:24px 20px 56px; }}
h1 {{ margin:0 0 10px; font-size:clamp(24px,4vw,38px); line-height:1.25; }}
h2 {{ margin:0 0 12px; padding-bottom:7px; border-bottom:1px solid var(--line); font-size:21px; }}
h3 {{ margin:0 0 8px; font-size:18px; }}
h4 {{ margin:0 0 5px; font-size:16px; }}
p {{ margin:7px 0; overflow-wrap:anywhere; word-break:break-word; }}
a {{ color:var(--blue); overflow-wrap:anywhere; }}
.hero {{ background:white; border:1px solid var(--line); border-top:5px solid {"var(--green)" if confirmable else "var(--red)"}; padding:20px; box-shadow:0 2px 8px #0f172a0d; }}
.state {{ display:inline-block; padding:4px 10px; border-radius:999px; font-weight:700; color:{"var(--green)" if confirmable else "var(--red)"}; background:{"var(--green-soft)" if confirmable else "var(--red-soft)"}; }}
.narrative {{ margin:16px 0; font-size:18px; font-weight:600; overflow-wrap:anywhere; word-break:break-word; }}
.meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px 18px; color:var(--muted); font-size:14px; }}
.meta code,.hash {{ display:block; overflow-wrap:anywhere; font-family:Consolas,"SFMono-Regular",monospace; font-size:12px; color:#334155; }}
code {{ overflow-wrap:anywhere; word-break:break-word; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:10px; margin-top:16px; }}
.stat {{ background:var(--blue-soft); border:1px solid #bfdbfe; padding:10px; text-align:center; }}
.stat strong {{ display:block; color:var(--blue); font-size:25px; line-height:1.1; }}
.stat span {{ color:#334155; font-size:13px; }}
  .blocking-note {{ padding:12px 14px; border-left:4px solid var(--red); background:var(--red-soft); color:#7f1d1d; font-weight:700; }}
 .testing-note {{ padding:12px 14px; border-left:4px solid var(--orange); background:var(--orange-soft); color:#9a3412; font-weight:700; }}
.section {{ background:white; border:1px solid var(--line); padding:18px; margin-top:18px; }}
.section.warning {{ border-left:4px solid var(--orange); background:var(--orange-soft); }}
.section.boundary {{ border-left:4px solid var(--blue); background:var(--blue-soft); }}
.muted {{ color:var(--muted); overflow-wrap:anywhere; }}
ul {{ margin:8px 0 0; padding-left:23px; }}
li {{ margin:5px 0; }}
li small {{ display:block; color:var(--muted); }}
.deliverable-group {{ margin:10px 0; border:1px solid var(--line); background:white; }}
details > summary {{ cursor:pointer; padding:12px 15px; font-weight:700; color:#1e3a8a; background:#f8fbff; }}
.artifact-item {{ display:flex; gap:14px; padding:14px; border-top:1px solid #e8edf3; }}
.artifact-body {{ min-width:0; flex:1; }}
.figure-preview {{ width:210px; max-height:160px; object-fit:contain; object-position:top center; border:1px solid var(--line); background:#fff; flex:0 0 auto; }}
.path,.subline {{ color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
.preview-table {{ margin-top:10px; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th,td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
th {{ background:#eef2f7; white-space:nowrap; }}
.hash {{ margin-top:8px; }}
.status {{ font-weight:700; }}
.status-pass,.status-supported {{ color:var(--green); }}
.status-fail,.status-missing,.status-blocked {{ color:var(--red); }}
.status-conditional_pass {{ color:var(--orange); }}
.two-col {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:18px; }}
.two-col > * {{ min-width:0; overflow-x:auto; }}
.confirm {{ border-left:4px solid {"var(--green)" if confirmable else "var(--red)"}; background:{"var(--green-soft)" if confirmable else "var(--red-soft)"}; }}
.route-section {{ border-left:4px solid var(--orange); background:var(--orange-soft); }}
.route-card {{ border:1px solid #fed7aa; background:#fff; padding:12px 14px; margin-top:10px; }}
.route-card h3 {{ color:#9a3412; }}
.route-card code {{ display:block; white-space:pre-wrap; overflow-wrap:anywhere; color:#334155; font-family:Consolas,"SFMono-Regular",monospace; font-size:12px; }}
@media (max-width:760px) {{ main {{ padding:14px 10px 40px; }} .artifact-item {{ display:block; }} .figure-preview {{ width:100%; max-height:none; margin-bottom:10px; }} .two-col {{ grid-template-columns:minmax(0,1fr); }} .two-col table {{ table-layout:fixed; width:100%; }} .two-col th {{ white-space:normal; word-break:break-word; }} table {{ min-width:0; }} .preview-table {{ overflow-x:auto; }} .preview-table table {{ min-width:680px; }} }}
</style>
</head>
<body><main>
<header class="hero">
<h1>{_text(summary.get("checkpoint_title_zh") or "Draftpaper 阶段成果审阅")}</h1>
 <span class="state">{_text(state_label)}</span>
 {warning}
 {test_note}
<p class="narrative">{_text(summary.get("stage_narrative_zh") or "本阶段摘要尚未登记。")}</p>
<p class="muted">{_text(metric_text)}</p>
<div class="stats">{stat_html}</div>
<div class="meta" style="margin-top:16px">
<div><strong>阶段：</strong>{_text(summary.get("completed_stage"))}</div>
<div><strong>摘要合同：</strong><code>{_text(summary.get("schema_version") or "未登记")}</code></div>
<div><strong>证据快照：</strong>{_text(identity.get("evidence_snapshot_id") or "未登记")}</div>
<div><strong>研究蓝图 hash：</strong><code>{_text(identity.get("plan_hash") or "未登记")}</code></div>
<div><strong>checkpoint hash：</strong><code>{_text(request.get("checkpoint_hash") or identity.get("checkpoint_hash") or "未登记")}</code></div>
</div>
</header>
{activity_html}
{baseline_html}
{key_findings}
{decision_routes}
{selected_route}
{boundaries}
<section class="section"><h2>本阶段完整成果</h2><p class="muted">以下内容是本阶段提交给用户确认的完整成果；即使某个文件相对上一快照未变化，也不会从本列表隐藏。</p>{_render_groups(root, output_dir, summary.get("deliverable_groups") or [])}</section>
<section class="section"><h2>本次相对上一快照的变化</h2>{_render_changes(root, output_dir, summary.get("transaction_changes") or {})}</section>
<section class="section"><h2>验证与一致性</h2>{_render_validation(root, output_dir, [*(summary.get("validation_summary") or []), *(summary.get("consistency_checks") or [])])}</section>
{unresolved}
{_render_evidence_identity(summary)}
<section class="section"><h2>请优先检查</h2>{primary_html}</section>
<section class="section confirm"><h2>本次确认意味着什么</h2><p>{_text(confirmation.get("meaning_zh") or summary.get("confirmation_meaning_zh"))}</p><p><strong>拒绝或要求修改：</strong>{_text(confirmation.get("refinement_route_zh") or summary.get("rejection_or_refinement_route_zh"))}</p><p><strong>确认命令：</strong>{command_html}</p></section>
<section class="section"><h2>证据与文件身份</h2><p>机器摘要：{json_html}　·　产物清单：{manifest_html}</p><p><strong>stage summary hash：</strong><code>{_text(summary.get("stage_summary_sha256") or request.get("stage_summary_sha256"))}</code></p><p><strong>摘要生成命令：</strong>{_text(summary.get("command"))}</p><p><strong>确认合同：</strong>{_text((summary.get("confirmation_contract") or {}).get("source_of_truth") or "未登记")}；用户确认要求：{_text((summary.get("confirmation_contract") or {}).get("requires_user_decision"))}</p></section>
</main></body></html>\n'''


_DECISION_LABELS = {
    "zh-CN": {
        "audit": "打开完整技术审计",
        "summary": "机器摘要",
        "contract": "确认合同",
        "readability": "可读性检查",
        "changed": "相对上次确认的变化",
        "confirming": "本次确认什么",
        "context": "样本、验证与主结果",
        "facts": "本次决定的关键事实",
        "figures": "主图支持的结论",
        "boundaries": "论断边界",
        "exclusions": "本次不确认什么",
        "reopen": "何时会重新要求科学确认",
        "deliverables": "本阶段可阅读产物",
        "meaning": "确认后的含义",
        "command": "确认命令",
        "evidence": "证据：",
        "first": "这是首次科学确认。",
        "no_figures": "本次没有主图作为独立科学决定项。",
        "no_deliverables": "本阶段未登记额外可阅读产物。",
        "no_command": "当前不需要新的作者确认命令；请查阅上方状态和连续性说明。",
        "continuity": "本次科学决定与最近一次作者确认一致，系统将沿用原确认；技术审计已更新，不需要重复输入确认 hash。",
        "changed_notice": "检测到科学决定变化。请先阅读下方变化说明，再决定是否确认、要求修订或拒绝。",
        "blocked_notice": "当前存在阻断或过期证据；页面可阅读，但不能用于确认。",
        "facts_note": "这些事实与下方陈述使用同一组 fact IDs；完整运行和审计细节见技术审计页。",
        "title": "Draftpaper 科学确认",
        "science": "科学决定：",
    },
    "en": {
        "audit": "Open technical audit",
        "summary": "Machine summary",
        "contract": "Confirmation contract",
        "readability": "Readability check",
        "changed": "What changed since the prior confirmation",
        "confirming": "What this decision confirms",
        "context": "Sample, validation, and primary result",
        "facts": "Key facts for this decision",
        "figures": "Conclusions supported by the main figures",
        "boundaries": "Claim boundaries",
        "exclusions": "What this decision does not confirm",
        "reopen": "When scientific confirmation is required again",
        "deliverables": "Readable outputs from this stage",
        "meaning": "What confirmation permits next",
        "command": "Confirmation command",
        "evidence": "Evidence: ",
        "first": "This is the first scientific confirmation.",
        "no_figures": "No main figure is an independent decision item in this checkpoint.",
        "no_deliverables": "No additional readable deliverable is registered for this stage.",
        "no_command": "No new author-confirmation command is required; review the status and continuity note above.",
        "continuity": "This scientific decision matches the latest author confirmation. The system preserves that decision while updating the technical audit; no repeated hash entry is required.",
        "changed_notice": "A scientific decision changed. Review the difference below before confirming, refining, or rejecting it.",
        "blocked_notice": "Evidence is blocked or stale. This page remains readable but cannot be confirmed.",
        "facts_note": "These facts use the same fact IDs as the statements below. The technical audit retains full run and provenance detail.",
        "title": "Draftpaper scientific confirmation",
        "science": "Scientific decision: ",
    },
}


def _labels(locale: str) -> dict[str, str]:
    return _DECISION_LABELS["en"] if locale == "en" else _DECISION_LABELS["zh-CN"]


def _statement_text(statement: dict[str, Any], locale: str) -> str:
    if locale == "en" and _text(statement.get("text_en")):
        return _text(statement.get("text_en"))
    return _text(statement.get("text_zh"))


def _semantic_delta_text(delta: dict[str, Any], locale: str) -> str:
    return _text(human_scientific_delta_summary(delta, locale=locale))


_DELTA_VALUE_LABELS = {
    "zh-CN": {
        "metric": "指标",
        "metric_definition_id": "指标定义",
        "value": "数值",
        "score": "得分",
        "estimate": "估计值",
        "cohort_id": "样本组",
        "entity_type": "计数对象",
        "count_mode": "计数口径",
        "filter_contract_id": "筛选口径",
        "run_id": "运行批次",
        "split_id": "验证划分",
        "model_id": "模型",
        "validation_design": "验证设计",
        "expected_cohort_id": "预期样本组",
        "expected_split_id": "预期验证划分",
        "caption_cohort_id": "图注样本组",
        "caption_split_id": "图注验证划分",
        "figure_cohort_id": "图表样本组",
        "figure_split_id": "图表验证划分",
        "plotted_series_ids": "图中绘制的数据序列",
        "caption_series_ids": "图注声明的数据序列",
        "claim_series_ids": "结论关联的数据序列",
        "figure_quantity_kind": "图表数据类型",
        "caption_quantity_kind": "图注数据类型",
        "claim_quantity_kind": "结论数据类型",
    },
    "en": {
        "metric": "Metric",
        "metric_definition_id": "Metric definition",
        "value": "Value",
        "score": "Score",
        "estimate": "Estimate",
        "cohort_id": "Cohort",
        "entity_type": "Counted entity",
        "count_mode": "Counting rule",
        "filter_contract_id": "Filter contract",
        "run_id": "Run",
        "split_id": "Validation split",
        "model_id": "Model",
        "validation_design": "Validation design",
        "expected_cohort_id": "Expected cohort",
        "expected_split_id": "Expected split",
        "caption_cohort_id": "Caption cohort",
        "caption_split_id": "Caption split",
        "figure_cohort_id": "Figure cohort",
        "figure_split_id": "Figure split",
        "plotted_series_ids": "Plotted series",
        "caption_series_ids": "Series named in caption",
        "claim_series_ids": "Series tied to claim",
        "figure_quantity_kind": "Figure quantity",
        "caption_quantity_kind": "Caption quantity",
        "claim_quantity_kind": "Claim quantity",
    },
}

_FACT_TYPE_LABELS = {
    "zh-CN": {
        "metric": "指标事实",
        "count": "样本计数",
        "figure": "图表证据",
        "finding": "研究发现",
        "claim_boundary": "论断边界",
        "identity": "研究身份",
        "scope": "确认范围",
    },
    "en": {
        "metric": "Metric fact",
        "count": "Sample count",
        "figure": "Figure evidence",
        "finding": "Finding",
        "claim_boundary": "Claim boundary",
        "identity": "Research identity",
        "scope": "Confirmation scope",
    },
}

_COHORT_LABELS = {
    "zh-CN": {
        "registered_2023_samples": "2023 年登记样本",
        "complete_aaew_records": "完整 AAEW 记录",
        "reference_polygons_complete_0_30_60_90m": "完整的 0、30、60、90 米缓冲参考地块",
        "anomaly_injection_2023": "2023 年异常注入样本",
    },
    "en": {
        "registered_2023_samples": "2023 registered samples",
        "complete_aaew_records": "complete AAEW records",
        "reference_polygons_complete_0_30_60_90m": "complete 0/30/60/90 m buffer reference polygons",
        "anomaly_injection_2023": "2023 anomaly-injection samples",
    },
}

_COUNT_VALUE_LABELS = {
    "entity_type": {
        "zh-CN": {
            "sample_record": "样本记录",
            "support_profile": "支持档案",
            "reference_polygon": "参考地块",
            "spatial_block": "空间区块",
            "reporting_unit": "报告单元",
            "anomaly_instance": "异常注入实例",
        },
        "en": {
            "sample_record": "sample records",
            "support_profile": "support profiles",
            "reference_polygon": "reference polygons",
            "spatial_block": "spatial blocks",
            "reporting_unit": "reporting units",
            "anomaly_instance": "injected anomalies",
        },
    },
    "count_mode": {
        "zh-CN": {
            "row_count": "记录总数",
            "post_filter_row_count": "筛选后记录数",
            "distinct_key_count": "不同档案数",
            "distinct_polygon_id_count": "唯一地块数",
            "distinct_group_count": "独立区块数",
            "distinct_reporting_unit_count": "独立报告单元数",
            "injection_instance_count": "注入实例数",
            "unique": "去重后数量",
        },
        "en": {
            "row_count": "total",
            "post_filter_row_count": "post-filter",
            "distinct_key_count": "distinct",
            "distinct_polygon_id_count": "unique",
            "distinct_group_count": "independent",
            "distinct_reporting_unit_count": "unique",
            "injection_instance_count": "injected",
            "unique": "unique",
        },
    },
}


def _is_digest(value: str) -> bool:
    normalized = value.removeprefix("sha256:").strip()
    return len(normalized) in {32, 40, 64} and all(character in "0123456789abcdefABCDEF" for character in normalized)


def _cohort_label(value: Any, *, locale: str) -> str:
    raw = str(value or "")
    slug = raw.partition(":")[2] if raw.startswith("cohort:") else raw
    label = _COHORT_LABELS["en" if locale == "en" else "zh-CN"].get(slug)
    if label:
        return label
    words = slug.replace("_", " ").strip()
    return words or ("未登记" if locale != "en" else "Not recorded")


def _count_label(field: str, value: Any, *, locale: str) -> str:
    language = "en" if locale == "en" else "zh-CN"
    return _COUNT_VALUE_LABELS.get(field, {}).get(language, {}).get(str(value), str(value).replace("_", " "))


def _format_count(value: Any, *, locale: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return _human_delta_value(value, locale=locale)


def _count_fact_description(value: dict[str, Any], *, locale: str) -> str:
    cohort = _cohort_label(value.get("cohort_id"), locale=locale)
    entity_key = str(value.get("entity_type") or "")
    entity = _count_label("entity_type", entity_key, locale=locale)
    mode = str(value.get("count_mode") or "")
    count = _format_count(value.get("value", value.get("count")), locale=locale)
    if locale == "en":
        mode_label = {
            "row_count": "total",
            "post_filter_row_count": "post-filter",
            "distinct_key_count": "distinct",
            "distinct_polygon_id_count": "unique",
            "distinct_group_count": "independent",
            "distinct_reporting_unit_count": "independent",
            "injection_instance_count": "controlled injected",
            "unique": "unique",
        }.get(mode, mode.replace("_", " "))
        return f"{count} {mode_label} {entity} in {cohort}"

    unit = {
        "sample_record": "条",
        "support_profile": "种",
        "reference_polygon": "个",
        "spatial_block": "个",
        "reporting_unit": "个",
        "anomaly_instance": "个",
    }.get(entity_key, "个")
    if mode == "row_count":
        return f"{cohort}共有 {count} {unit}{entity}"
    if mode == "post_filter_row_count":
        return f"{cohort}筛选后保留 {count} {unit}{entity}"
    mode_label = {
        "distinct_key_count": "不同",
        "distinct_polygon_id_count": "唯一",
        "distinct_group_count": "独立",
        "distinct_reporting_unit_count": "独立",
        "injection_instance_count": "受控注入",
        "unique": "去重后",
    }.get(mode, mode.replace("_", " "))
    return f"{cohort}：{count} {unit}{mode_label}{entity}"


def _human_delta_value(value: Any, *, locale: str) -> str:
    if value is None or value == "":
        return "未登记" if locale != "en" else "Not recorded"
    if isinstance(value, bool):
        return ("是" if value else "否") if locale != "en" else ("Yes" if value else "No")
    if isinstance(value, str):
        if _is_digest(value):
            return "内容身份指纹已变化" if locale != "en" else "Content identity fingerprint changed"
        return value
    if isinstance(value, dict):
        parts = []
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            normalized_key = str(key)
            if normalized_key.endswith(("sha256", "_hash")) or normalized_key == "filter_contract_id":
                continue
            label = _DELTA_VALUE_LABELS["en" if locale == "en" else "zh-CN"].get(normalized_key)
            label = label or normalized_key.replace("_", " ")
            if normalized_key == "cohort_id":
                rendered = _cohort_label(item, locale=locale)
            elif normalized_key in {"entity_type", "count_mode"}:
                rendered = _count_label(normalized_key, item, locale=locale)
            else:
                rendered = _human_delta_value(item, locale=locale)
            parts.append(f"{label}: {rendered}")
        if parts:
            return "; ".join(parts)
        return "科学内容指纹已变化" if locale != "en" else "Scientific content fingerprint changed"
    if isinstance(value, (list, tuple)):
        rendered = [_human_delta_value(item, locale=locale) for item in value]
        rendered = [item for item in rendered if item]
        return "、".join(rendered) if locale != "en" else ", ".join(rendered)
    return str(value)


def _canonical_delta_item(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fact_identity(item: dict[str, Any]) -> str:
    kind = str(item.get("fact_type") or "fact")
    value = item.get("semantic_value")
    if isinstance(value, dict):
        if kind == "figure":
            identity = {"figure_id": value.get("figure_id")}
        elif kind == "count":
            identity = {key: item_value for key, item_value in value.items() if key not in {"value", "count", "n"}}
        elif kind == "metric":
            identity = {
                key: item_value
                for key, item_value in value.items()
                if key not in {"value", "score", "estimate", "metric_value", "metric_result"}
            }
        else:
            identity = value
    else:
        identity = value
    return f"{kind}:{_canonical_delta_item(identity)}"


def _fact_description(item: dict[str, Any], *, locale: str) -> str:
    kind = str(item.get("fact_type") or "fact")
    type_label = _FACT_TYPE_LABELS["en" if locale == "en" else "zh-CN"].get(kind, "Fact" if locale == "en" else "事实")
    value = item.get("semantic_value")
    if kind == "figure" and isinstance(value, dict):
        figure_id = _human_delta_value(value.get("figure_id"), locale=locale)
        note = "图表内容或语义发生变化，请与下方本次主图预览对照。" if locale != "en" else "Figure content or meaning changed; compare with the current figure preview below."
        return f"{type_label}“{figure_id}”：{note}" if locale != "en" else f'{type_label} "{figure_id}": {note}'
    if kind == "count" and isinstance(value, dict):
        return f"{type_label}: {_count_fact_description(value, locale=locale)}" if locale == "en" else f"{type_label}：{_count_fact_description(value, locale=locale)}。"
    if kind == "metric" and isinstance(value, dict):
        labels = _DELTA_VALUE_LABELS["en" if locale == "en" else "zh-CN"]
        name = value.get("metric") or value.get("metric_definition_id") or value.get("name")
        measured = value.get("value", value.get("score", value.get("estimate")))
        details = [f"{labels['metric']}: {_human_delta_value(name, locale=locale)}"] if name else []
        if measured is not None:
            details.append(f"{labels['value']}: {_human_delta_value(measured, locale=locale)}")
        for key in ("cohort_id", "model_id", "run_id", "split_id"):
            if value.get(key) not in (None, ""):
                details.append(f"{labels[key]}: {_human_delta_value(value[key], locale=locale)}")
        return f"{type_label}：" + "；".join(details) if locale != "en" else f"{type_label}: " + "; ".join(details)
    rendered = _human_delta_value(value, locale=locale)
    return f"{type_label}：{rendered}" if locale != "en" else f"{type_label}: {rendered}"


def _render_fact_list_delta(before: list[Any], after: list[Any], *, locale: str) -> str:
    before_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    after_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in before:
        if isinstance(item, dict):
            before_groups[_fact_identity(item)].append(item)
    for item in after:
        if isinstance(item, dict):
            after_groups[_fact_identity(item)].append(item)

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    updated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for identity in sorted(set(before_groups) | set(after_groups)):
        old_items = sorted(before_groups.get(identity, []), key=_canonical_delta_item)
        new_items = sorted(after_groups.get(identity, []), key=_canonical_delta_item)
        old_counts = Counter(_canonical_delta_item(item.get("semantic_value")) for item in old_items)
        new_counts = Counter(_canonical_delta_item(item.get("semantic_value")) for item in new_items)
        old_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
        new_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in old_items:
            old_exact[_canonical_delta_item(item.get("semantic_value"))].append(item)
        for item in new_items:
            new_exact[_canonical_delta_item(item.get("semantic_value"))].append(item)
        old_left = [item for key, items in old_exact.items() for item in items[max(0, new_counts[key]):]]
        new_left = [item for key, items in new_exact.items() for item in items[max(0, old_counts[key]):]]
        paired = min(len(old_left), len(new_left))
        updated.extend(zip(old_left[:paired], new_left[:paired]))
        removed.extend(old_left[paired:])
        added.extend(new_left[paired:])

    rows = []
    for old_item, new_item in updated:
        kind = str(new_item.get("fact_type") or "fact")
        old_value = old_item.get("semantic_value")
        new_value = new_item.get("semantic_value")
        if kind == "figure":
            description = _fact_description(new_item, locale=locale)
        else:
            description = (
                f"{_FACT_TYPE_LABELS['en' if locale == 'en' else 'zh-CN'].get(kind, 'Fact' if locale == 'en' else '事实')}："
                f"{_human_delta_value(old_value, locale=locale)} → {_human_delta_value(new_value, locale=locale)}"
            )
        rows.append(f"<li><strong>{'更新：' if locale != 'en' else 'Updated: '}</strong>{_text(description)}</li>")
    for item in added:
        prefix = "新增：" if locale != "en" else "Added: "
        rows.append(f"<li><strong>{prefix}</strong>{_text(_fact_description(item, locale=locale))}</li>")
    for item in removed:
        prefix = "移除：" if locale != "en" else "Removed: "
        rows.append(f"<li><strong>{prefix}</strong>{_text(_fact_description(item, locale=locale))}</li>")

    if not rows:
        return '<p class="muted">事实列表顺序或机器身份有变化，但未发现具体事实内容差异；请核对本页列出的当前事实。</p>' if locale != "en" else '<p class="muted">Only list ordering or machine identity changed; no fact-content difference was found. Review the current facts on this page.</p>'
    summary = (
        f"新增 {len(added)} 项、更新 {len(updated)} 项、移除 {len(removed)} 项。"
        if locale != "en"
        else f"{len(added)} added, {len(updated)} updated, {len(removed)} removed."
    )
    heading = "具体变化" if locale != "en" else "Itemized changes"
    return f'<p class="delta-count">{summary}</p><h4>{heading}</h4><ul class="delta-list">{"".join(rows)}</ul>'


_FIGURE_DELTA_FIELDS = (
    "expected_cohort_id",
    "expected_split_id",
    "caption_cohort_id",
    "caption_split_id",
    "figure_cohort_id",
    "figure_split_id",
    "plotted_series_ids",
    "caption_series_ids",
    "claim_series_ids",
    "figure_quantity_kind",
    "caption_quantity_kind",
    "claim_quantity_kind",
)


def _figure_claim_identity(item: dict[str, Any]) -> tuple[str, str]:
    return str(item.get("claim_statement_id") or ""), str(item.get("figure_id") or "")


def _figure_display_name(item: dict[str, Any], locale: str, brief: dict[str, Any] | None = None) -> str:
    claim_id = str(item.get("claim_statement_id") or "")
    suffix = claim_id.removeprefix("figure-")
    claims = (brief or {}).get("figure_claims") or []
    claim = next(
        (
            row
            for row in claims
            if isinstance(row, dict)
            and isinstance(row.get("statement"), dict)
            and str(row["statement"].get("statement_id") or "") == claim_id
        ),
        {},
    )
    title = str(claim.get("figure_id") or item.get("caption") or item.get("figure_id") or "")
    if suffix.isdigit():
        figure_number = f"Figure {suffix}" if locale == "en" else f"图 {suffix}"
        return f"{figure_number}: {title}" if title else figure_number
    return title or claim_id or ("figure" if locale == "en" else "图表")


def _figure_anchor_id(statement_id: str) -> str:
    safe_id = "".join(char if char.isalnum() or char in "-_" else "-" for char in statement_id)
    return f"figure-evidence-{safe_id or 'current'}"


def _figure_claim_change(old: dict[str, Any], new: dict[str, Any], *, brief: dict[str, Any], locale: str) -> str:
    labels = _DELTA_VALUE_LABELS["en" if locale == "en" else "zh-CN"]
    notes = []
    if old.get("figure_semantic_sha256") != new.get("figure_semantic_sha256"):
        notes.append(
            "图表产物内容发生变化；本次确认记录未附上一版图像预览，无法仅凭记录说明图像细节差异。请核对当前图表，并与此前留存版本对照。"
            if locale != "en"
            else "The figure artifact changed. This confirmation record does not include the prior image, so its visual differences cannot be described from this record alone. Review the current figure and compare it with the prior version you retained."
        )
    for field in _FIGURE_DELTA_FIELDS:
        if old.get(field) == new.get(field):
            continue
        before = _human_delta_value(old.get(field), locale=locale)
        after = _human_delta_value(new.get(field), locale=locale)
        label = labels.get(field, field.replace("_", " "))
        notes.append(f"{label}: {before} → {after}")
    if not notes:
        notes.append("对应的科研字段发生变化；请核对该图及其支持的结论。" if locale != "en" else "A scientific field changed; review this figure and its supported claim.")
    statement_id = str(new.get("claim_statement_id") or old.get("claim_statement_id") or "")
    claim = next(
        (
            row
            for row in brief.get("figure_claims") or []
            if isinstance(row, dict)
            and isinstance(row.get("statement"), dict)
            and str(row["statement"].get("statement_id") or "") == statement_id
        ),
        {},
    )
    statement = claim.get("statement") if isinstance(claim.get("statement"), dict) else {}
    claim_text = _statement_text(statement, locale) if statement else ""
    anchor_id = _figure_anchor_id(statement_id)
    link_label = "查看当前图表与对应说明" if locale != "en" else "View the current figure and its explanation"
    rows = [f"<li>{_text(note)}</li>" for note in notes]
    if claim_text:
        label = "当前图表所对应的说明：" if locale != "en" else "Current figure explanation: "
        rows.append(f"<li>{label}{_text(claim_text)}</li>")
    rows.append(f'<li><a href="#{escape(anchor_id)}">{link_label}</a></li>')
    title = _figure_display_name(new, locale, brief)
    return f"<li><strong>{_text(title)}</strong><ul>{''.join(rows)}</ul></li>"


def _render_figure_map_delta(before: list[Any], after: list[Any], *, brief: dict[str, Any], locale: str) -> str:
    old_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    new_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in before:
        if isinstance(item, dict):
            old_groups[_figure_claim_identity(item)].append(item)
    for item in after:
        if isinstance(item, dict):
            new_groups[_figure_claim_identity(item)].append(item)

    rows = []
    for identity in sorted(set(old_groups) | set(new_groups)):
        old_items = sorted(old_groups.get(identity, []), key=_canonical_delta_item)
        new_items = sorted(new_groups.get(identity, []), key=_canonical_delta_item)
        old_exact = Counter(_canonical_delta_item(item) for item in old_items)
        new_exact = Counter(_canonical_delta_item(item) for item in new_items)
        unchanged = old_exact & new_exact
        old_seen: Counter[str] = Counter()
        new_seen: Counter[str] = Counter()
        old_left = []
        new_left = []
        for item in old_items:
            key = _canonical_delta_item(item)
            old_seen[key] += 1
            if old_seen[key] > unchanged[key]:
                old_left.append(item)
        for item in new_items:
            key = _canonical_delta_item(item)
            new_seen[key] += 1
            if new_seen[key] > unchanged[key]:
                new_left.append(item)
        # Each remaining row shares its claim and figure identity, so it is a semantic update.
        paired = min(len(old_left), len(new_left))
        for old, new in zip(old_left[:paired], new_left[:paired]):
            rows.append(_figure_claim_change(old, new, brief=brief, locale=locale))
        for item in new_left[paired:]:
            prefix = "新增图表与论断绑定：" if locale != "en" else "Added figure-to-claim binding: "
            rows.append(f"<li><strong>{prefix}{_text(_figure_display_name(item, locale, brief))}</strong></li>")
        for item in old_left[paired:]:
            prefix = "移除图表与论断绑定：" if locale != "en" else "Removed figure-to-claim binding: "
            rows.append(f"<li><strong>{prefix}{_text(_figure_display_name(item, locale, brief))}</strong></li>")

    if not rows:
        return '<p class="muted">未发现图表与论断关系的具体变化。</p>' if locale != "en" else '<p class="muted">No specific figure-to-claim change was found.</p>'
    heading = "图表级变化" if locale != "en" else "Figure-level changes"
    return f'<h4>{heading}</h4><ul class="delta-list">{"".join(rows)}</ul>'


def _render_semantic_list_delta(before: list[Any], after: list[Any], *, locale: str) -> str:
    # Cancel exact matches as a multiset: repeated entries and their removal
    # remain meaningful, but unchanged statements need not be printed twice.
    common = Counter(map(_canonical_delta_item, before)) & Counter(map(_canonical_delta_item, after))
    residuals = []
    for values in (before, after):
        remaining = common.copy()
        changed = []
        for value in values:
            key = _canonical_delta_item(value)
            if remaining[key]:
                remaining[key] -= 1
            else:
                changed.append(value)
        residuals.append(changed)
    old, new = residuals
    if not old and not new:
        note = "仅列表顺序变化；科学内容未变化。" if locale != "en" else "Only list ordering changed; the scientific content is unchanged."
        return f'<p class="muted">{note}</p>'
    old_text = _human_delta_value(old, locale=locale)
    new_text = _human_delta_value(new, locale=locale)
    if old_text == new_text:
        note = (
            "对应的科学内容身份发生变化；请核对当前图表、方法或运行证据。"
            if locale != "en"
            else "The scientific content identity changed; review the current figure, method, or run evidence."
        )
        return f"<p>{_text(new_text)}</p><p>{note}</p>"
    previous_label = "移除或更新前" if locale != "en" else "Removed or previous"
    current_label = "新增或更新后" if locale != "en" else "Added or current"
    parts = []
    if old:
        parts.append(f"<p><strong>{previous_label}:</strong> {_text(old_text)}</p>")
    if new:
        parts.append(f"<p><strong>{current_label}:</strong> {_text(new_text)}</p>")
    return "".join(parts)


def _render_semantic_change(item: dict[str, Any], *, brief: dict[str, Any], locale: str) -> str:
    field = str(item.get("field") or "")
    before, after = item.get("before"), item.get("after")
    label = scientific_delta_field_label(field, locale=locale)
    if field.endswith(".facts") and isinstance(before, list) and isinstance(after, list):
        detail = _render_fact_list_delta(before, after, locale=locale)
    elif field == "figure_claim_map" and isinstance(before, list) and isinstance(after, list):
        detail = _render_figure_map_delta(before, after, brief=brief, locale=locale)
    elif (
        field in {
            "decision_brief.semantic_subject.confirming",
            "decision_brief.semantic_subject.not_confirming",
            "decision_brief.semantic_subject.claim_boundaries",
            "decision_brief.semantic_subject.figure_claims",
            "decision_brief.semantic_subject.reopen_conditions",
        }
        and isinstance(before, list)
        and isinstance(after, list)
    ):
        detail = _render_semantic_list_delta(before, after, locale=locale)
    elif isinstance(before, str) and isinstance(after, str) and (_is_digest(before) or _is_digest(after)):
        suffix = "对应的科学内容身份已变化，请核对上方的研究蓝图、方法或运行范围。" if locale != "en" else "Its scientific content identity changed; verify the corresponding blueprint, method, or run shown above."
        detail = f"<p>{_text(label)}{_text(suffix)}</p>"
    else:
        before_text = _human_delta_value(before, locale=locale)
        after_text = _human_delta_value(after, locale=locale)
        arrow = " → "
        detail = f'<p><strong>{"确认前" if locale != "en" else "Previously"}:</strong> {_text(before_text)}{arrow}<strong>{"本次" if locale != "en" else "Now"}:</strong> {_text(after_text)}</p>'
    return f'<article class="delta-change"><h3>{_text(label)}</h3>{detail}</article>'


def _brief_ref_links(root: Path, output_dir: Path, refs: list[Any], *, locale: str = "zh-CN") -> str:
    """Render compact, copyable evidence locators for the decision page.

    A decision brief can reuse the same canonical artifact across many facts
    and statements.  Turning each repeated locator into an anchor made normal
    research-plan pages exceed the author-page link budget, even though the
    page already exposes the key deliverables and figures as links.  Keep the
    full clickable artifact trail in the technical audit; the decision page
    retains the exact, safe artifact locator as inline text.
    """

    labels = _labels(locale)
    links = []
    for raw in refs[:5]:
        ref = str(raw or "")
        if ref.startswith("artifact:"):
            relative = ref[len("artifact:") :]
            links.append(f'<code class="artifact-ref">{_text(relative)}</code>')
        elif ref.startswith("policy:"):
            links.append(labels["contract"])
        else:
            links.append(_text(ref))
    return "、".join(links)


def _brief_statements(root: Path, output_dir: Path, statements: list[Any], *, locale: str = "zh-CN") -> str:
    labels = _labels(locale)
    rows = []
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        refs = [*list(statement.get("evidence_refs") or []), *list(statement.get("claim_refs") or [])]
        ref_html = _brief_ref_links(root, output_dir, refs, locale=locale)
        statement_id = escape(_text(statement.get("statement_id")))
        fact_refs = escape(" ".join(_text(item) for item in statement.get("fact_refs") or []))
        rows.append(
            f'<li data-statement-id="{statement_id}" data-fact-refs="{fact_refs}"><span>'
            + _statement_text(statement, locale)
            + "</span>"
            + (f'<small class="refs">{labels["evidence"]}{ref_html}</small>' if ref_html else "")
            + "</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>" if rows else '<p class="muted">未登记。</p>'


def _brief_facts(root: Path, output_dir: Path, brief: dict[str, Any], *, locale: str) -> str:
    labels = _labels(locale)
    fact_ids = [
        *list((brief.get("scientific_context") or {}).get("identity_fact_refs") or []),
        *list((brief.get("scientific_context") or {}).get("metric_fact_refs") or []),
        *list((brief.get("scientific_context") or {}).get("count_fact_refs") or []),
    ]
    facts = {str(item.get("fact_id") or ""): item for item in brief.get("facts") or [] if isinstance(item, dict)}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact_id in dict.fromkeys(str(value) for value in fact_ids if str(value)):
        fact = facts.get(fact_id)
        if not fact:
            continue
        # Coalesce display only when every field except the record ID agrees.
        # Equal values with different labels, semantics or sources stay separate.
        key = _canonical_delta_item({name: value for name, value in fact.items() if name != "fact_id"})
        groups[key].append(fact)
    rows = []
    for group in groups.values():
        fact = group[0]
        fact_id = str(fact.get("fact_id") or "")
        fact_refs = escape(" ".join(str(item.get("fact_id") or "") for item in group))
        value = fact.get("value")
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else _text(value)
        refs = _brief_ref_links(root, output_dir, list(fact.get("evidence_refs") or []), locale=locale)
        label = _text(fact.get("label_en")) if locale == "en" else _text(fact.get("label_zh"))
        rows.append(
            f'<li data-fact-id="{escape(fact_id)}" data-fact-refs="{fact_refs}"><strong>{label}</strong>：{rendered}'
            + (f'<small class="refs">{labels["evidence"]}{refs}</small>' if refs else "")
            + "</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>" if rows else '<p class="muted">No structured identity fact is registered.</p>'


def render_checkpoint_decision_html(
    root: Path,
    output_dir: Path,
    summary: dict[str, Any],
    request: dict[str, Any],
    *,
    locale: str = "zh-CN",
) -> str:
    """Render the compact, evidence-bound page that the author actually reads."""

    locale = "en" if locale == "en" else "zh-CN"
    labels = _labels(locale)
    brief = summary.get("decision_brief") if isinstance(summary.get("decision_brief"), dict) else {}
    state = str(summary.get("review_state") or "confirmable")
    state_label = (_STATE_LABELS_EN if locale == "en" else _STATE_LABELS).get(state, state)
    continuity = summary.get("confirmation_continuity") if isinstance(summary.get("confirmation_continuity"), dict) else {}
    delta = brief.get("semantic_delta") if isinstance(brief.get("semantic_delta"), dict) else {}
    decision_question = brief.get("decision_question") if isinstance(brief.get("decision_question"), dict) else {}
    audit_name = "stage_audit.json" if summary.get("schema_version") == "dpl.checkpoint_summary.v6" else "stage_audit.zh-CN.html"
    audit_href = _link(root, output_dir, audit_name)
    summary_href = _link(root, output_dir, str(summary.get("stage_summary_path") or ""))
    request_href = _link(root, output_dir, "confirmation_request.json")
    readability_href = _link(root, output_dir, "checkpoint_readability_report.en.json" if locale == "en" else "checkpoint_readability_report.json")
    confirmation_command = request.get("confirmation_command") if (summary.get("confirmation_contract") or {}).get("confirmation_command_allowed") else None
    continuity_note = ""
    if continuity.get("eligible"):
        continuity_note = f'<p class="notice success">{labels["continuity"]}</p>'
    elif delta.get("classification") == "scientific_change":
        continuity_note = f'<p class="notice warning">{labels["changed_notice"]}</p>'
    elif state != "confirmable":
        continuity_note = f'<p class="notice warning">{labels["blocked_notice"]}</p>'
    candidate_hash = str(summary.get("revision_candidate_sha256") or "")
    candidate_meta = (
        f'<span>{"Revision candidate packet SHA-256" if locale == "en" else "本次修订候选包 SHA-256"}'
        f'<code>{_text(candidate_hash)}</code></span>'
        if candidate_hash
        else ""
    )
    figures = []
    for item in brief.get("figure_claims") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("project_relative_path") or "")
        statement = item.get("statement") if isinstance(item.get("statement"), dict) else {}
        figure_anchor = _figure_anchor_id(str(statement.get("statement_id") or ""))
        href = _link(root, output_dir, path)
        figures.append(
            f'<article id="{escape(figure_anchor)}" class="figure" data-statement-id="{escape(_text(statement.get("statement_id")))}" data-fact-refs="{escape(" ".join(_text(value) for value in statement.get("fact_refs") or []))}">'
            f'<h3>{_text(item.get("figure_id"))}</h3>'
            + (f'<a href="{href}"><img src="{href}" alt="{_text(item.get("figure_id"))}"></a>' if href and Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"} else "")
            + f'<p>{_statement_text(statement, locale)}</p>'
            + (f'<small class="refs">{labels["evidence"]}{_brief_ref_links(root, output_dir, list(statement.get("evidence_refs") or []), locale=locale)}</small>' if statement.get("evidence_refs") else "")
            + "</article>"
        )
    figure_html = "".join(figures) or f'<p class="muted">{labels["no_figures"]}</p>'
    changes = []
    for item in delta.get("changes") or []:
        if not isinstance(item, dict):
            continue
        changes.append(_render_semantic_change(item, brief=brief, locale=locale))
    change_note = (
        '<p class="muted">这里解释科学内容如何变化；哈希只用于技术审计，不代替文字说明。</p>'
        if changes and locale != "en"
        else '<p class="muted">This section explains the scientific changes in words; hashes are audit identifiers, not explanations.</p>'
        if changes
        else ""
    )
    change_html = ('<div class="delta-changes">' + "".join(changes) + "</div>" + change_note) if changes else ""
    deliverables = []
    for item in brief.get("latest_user_visible_deliverables") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("project_relative_path") or "")
        href = _link(root, output_dir, path)
        deliverables.append(
            f'<li><a href="{href}">{_text(item.get("title_zh") or path)}</a>'
            f'<small>{_text(item.get("purpose_zh"))}</small></li>'
        )
    deliverable_html = "<ul>" + "".join(deliverables) + "</ul>" if deliverables else f'<p class="muted">{labels["no_deliverables"]}</p>'
    confirmation_html = (
        f'<code>{_text(confirmation_command)}</code>'
        if confirmation_command
        else f'<p class="muted">{labels["no_command"]}</p>'
    )
    return f'''<!doctype html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_text(summary.get("checkpoint_title_en") if locale == "en" else summary.get("checkpoint_title_zh")) or labels["title"]}</title>
<style>
:root {{ --ink:#172033; --muted:#526071; --line:#d4dce7; --paper:#fff; --bg:#f6f8fb; --blue:#155eab; --blue-bg:#edf6ff; --green:#137333; --green-bg:#ecfdf3; --amber:#9a5800; --amber-bg:#fff8e8; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif; line-height:1.64; }}
main {{ max-width:980px; margin:0 auto; padding:26px 18px 56px; }} h1 {{ margin:0 0 9px; font-size:30px; line-height:1.25; }} h2 {{ margin:0 0 12px; font-size:20px; }} h3 {{ margin:0 0 7px; font-size:16px; }}
p {{ overflow-wrap:anywhere; }} a {{ color:var(--blue); overflow-wrap:anywhere; }} code {{ display:block; padding:10px; border:1px solid var(--line); background:#f8fafc; white-space:pre-wrap; overflow-wrap:anywhere; font-family:Consolas,"SFMono-Regular",monospace; font-size:12px; }} .refs code.artifact-ref {{ display:inline; padding:0; border:0; background:transparent; font-size:inherit; }}
.hero,.section {{ background:var(--paper); border:1px solid var(--line); border-radius:6px; padding:20px; }} .hero {{ border-top:5px solid var(--blue); }} .section {{ margin-top:16px; }} .status {{ display:inline-block; padding:3px 9px; background:var(--blue-bg); color:var(--blue); font-weight:700; border-radius:4px; }}
.lead {{ margin:14px 0 0; font-size:18px; font-weight:600; }} .muted,small {{ color:var(--muted); }} .notice {{ padding:11px 13px; border-left:4px solid var(--amber); background:var(--amber-bg); font-weight:600; }} .notice.success {{ border-color:var(--green); background:var(--green-bg); color:#14532d; }}
ul {{ margin:8px 0 0; padding-left:22px; }} li {{ margin:8px 0; }} li .refs,li small {{ display:block; margin-top:3px; }} .refs {{ font-size:12px; }} .figure-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }} .figure {{ border:1px solid var(--line); padding:13px; min-width:0; }} .figure img {{ display:block; width:100%; max-height:230px; object-fit:contain; border:1px solid #e3e9f1; background:white; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:14px; color:var(--muted); font-size:13px; }} .meta a {{ font-weight:600; }}
.delta-change {{ margin:14px 0; padding:14px; border-left:4px solid var(--blue); background:#f8fafc; min-width:0; }} .delta-change h3 {{ margin:0 0 8px; }} .delta-count {{ margin:4px 0 8px; font-weight:700; }} .delta-list {{ margin-top:6px; }} .delta-list ul {{ margin-top:5px; }}
@media (max-width:680px) {{ main {{ padding:14px 10px 42px; }} .hero,.section {{ padding:15px; }} h1 {{ font-size:25px; }} .figure-grid {{ grid-template-columns:minmax(0,1fr); }} .figure img {{ max-height:none; }} }}
</style>
</head>
<body><main>
<header class="hero">
<span class="status">{_text(state_label)}</span>
<h1>{_text(summary.get("checkpoint_title_en") if locale == "en" else summary.get("checkpoint_title_zh")) or labels["title"]}</h1>
<p class="lead" data-statement-id="{escape(_text(decision_question.get("statement_id")))}" data-fact-refs="{escape(" ".join(_text(value) for value in decision_question.get("fact_refs") or []))}">{_statement_text(decision_question, locale) or _text(summary.get("stage_purpose_zh"))}</p>
{continuity_note}
<div class="meta"><span>{labels["science"]}<code>{_text((summary.get("scientific_decision_fingerprint") or {}).get("scientific_decision_sha256"))}</code></span>{candidate_meta}<a href="{audit_href}">{labels["audit"]}</a><a href="{summary_href}">{labels["summary"]}</a><a href="{request_href}">{labels["contract"]}</a><a href="{readability_href}">{labels["readability"]}</a></div>
</header>
<section class="section"><h2>{labels["changed"]}</h2><p>{_semantic_delta_text(delta, locale) or labels["first"]}</p>{change_html}</section>
<section class="section"><h2>{labels["confirming"]}</h2>{_brief_statements(root, output_dir, list(brief.get("confirming") or []), locale=locale)}</section>
<section class="section"><h2>{labels["facts"]}</h2>{_brief_facts(root, output_dir, brief, locale=locale)}<p class="muted">{labels["facts_note"]}</p></section>
<section class="section"><h2>{labels["context"]}</h2>{_brief_statements(root, output_dir, list(brief.get("key_findings") or []), locale=locale)}</section>
<section class="section"><h2>{labels["figures"]}</h2><div class="figure-grid">{figure_html}</div></section>
<section class="section"><h2>{labels["boundaries"]}</h2>{_brief_statements(root, output_dir, list(brief.get("claim_boundaries") or []), locale=locale)}</section>
<section class="section"><h2>{labels["exclusions"]}</h2>{_brief_statements(root, output_dir, list(brief.get("not_confirming") or []), locale=locale)}</section>
<section class="section"><h2>{labels["reopen"]}</h2>{_brief_statements(root, output_dir, list(brief.get("reopen_conditions") or []), locale=locale)}</section>
<section class="section"><h2>{labels["deliverables"]}</h2>{deliverable_html}</section>
<section class="section"><h2>{labels["meaning"]}</h2>{_brief_statements(root, output_dir, list(brief.get("downstream_effects") or []), locale=locale)}<p><strong>{labels["command"]}</strong></p>{confirmation_html}</section>
</main></body></html>\n'''


def render_checkpoint_html(
    root: Path,
    output_dir: Path,
    summary: dict[str, Any],
    request: dict[str, Any],
    *,
    locale: str = "zh-CN",
) -> str:
    """Render the decision view for v5/v6 and retain the v3/v4 audit renderer."""

    if summary.get("schema_version") in {"dpl.checkpoint_summary.v5", "dpl.checkpoint_summary.v6"}:
        return render_checkpoint_decision_html(root, output_dir, summary, request, locale=locale)
    return render_checkpoint_audit_html(root, output_dir, summary, request)
