"""Offline HTML rendering for human checkpoint summaries."""

from __future__ import annotations

import os
import json
from html import escape
from pathlib import Path
from typing import Any


_STATE_LABELS = {
    "confirmable": "可以确认",
    "stale": "证据已过期",
    "blocked": "存在阻断问题",
    "preview_only": "仅预览，不可确认",
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
        + receipt_html
        + (f'<table><tbody>{rows}</tbody></table>' if rows else '<p class="muted">当前尚未绑定科学基线；这是首轮或旧项目迁移状态。</p>')
        + '</section>'
    )


def render_checkpoint_html(root: Path, output_dir: Path, summary: dict[str, Any], request: dict[str, Any]) -> str:
    """Render one portable, self-contained Chinese checkpoint review page."""

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
