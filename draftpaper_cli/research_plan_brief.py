"""Build and render the author-facing research-plan decision brief."""

from __future__ import annotations

import hashlib
import os
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping

from .artifact_identity import canonical_json


RESEARCH_PLAN_BRIEF_SCHEMA = "dpl.research_plan_decision_brief.v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any, *, limit: int = 1000) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _pick(row: Mapping[str, Any], key: str, *, locale: str) -> str:
    variants = (
        (f"{key}_zh_cn", f"{key}_zh", key, f"{key}_en")
        if locale == "zh-CN"
        else (f"{key}_en", f"{key}_en_us", key, f"{key}_zh_cn")
    )
    for variant in variants:
        value = row.get(variant)
        if value not in (None, "", [], {}):
            return _text(value)
    return ""


def _join(value: Any, *, locale: str = "zh-CN") -> str:
    if isinstance(value, (list, tuple, set)):
        values = [_text(item, limit=160) for item in value if _text(item, limit=160)]
        return ("、" if locale == "zh-CN" else ", ").join(values)
    return _text(value, limit=500)


def _claim_rows(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    blueprint = contracts.get("research_blueprint") or {}
    claim_contract = contracts.get("claim_contract") or {}
    rows = _rows(claim_contract.get("claims")) or _rows(blueprint.get("research_claims"))
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        result.append(
            {
                "claim_id": _text(row.get("claim_id") or row.get("id") or f"claim-{index}"),
                "research_question": _pick(row, "research_question", locale="en"),
                "research_question_zh": _pick(row, "research_question", locale="zh-CN"),
                "expected_finding": _pick(row, "expected_finding", locale="en"),
                "expected_finding_zh": _pick(row, "expected_finding", locale="zh-CN"),
                "boundary": _pick(row, "scientific_claim_boundary", locale="en")
                or _pick(row, "claim_boundary", locale="en"),
                "boundary_zh": _pick(row, "scientific_claim_boundary", locale="zh-CN")
                or _pick(row, "claim_boundary", locale="zh-CN"),
                "evidence_refs": ["research_plan/claim_contract.json"],
            }
        )
    return result


def _figure_rows(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    storyboard = contracts.get("figure_storyboard") or {}
    blueprint = contracts.get("research_blueprint") or {}
    rows = _rows(storyboard.get("figures"))
    if not rows:
        nested = blueprint.get("figure_storyboard") if isinstance(blueprint.get("figure_storyboard"), Mapping) else {}
        rows = _rows(nested.get("figures"))
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        result.append(
            {
                "figure_id": _text(row.get("figure_id") or row.get("id") or f"figure-{index}"),
                "title": _pick(row, "proposed_title", locale="en") or _pick(row, "title", locale="en"),
                "title_zh": _pick(row, "proposed_title", locale="zh-CN") or _pick(row, "title", locale="zh-CN"),
                "question": _pick(row, "research_question", locale="en"),
                "question_zh": _pick(row, "research_question", locale="zh-CN"),
                "expected": _pick(row, "expected_finding", locale="en"),
                "expected_zh": _pick(row, "expected_finding", locale="zh-CN"),
                "boundary": _pick(row, "scientific_claim_boundary", locale="en"),
                "boundary_zh": _pick(row, "scientific_claim_boundary", locale="zh-CN"),
                "required_data": list(row.get("required_data") or row.get("required_data_roles") or []),
                "required_method": list(row.get("required_method") or row.get("required_methods") or []),
                "panels": _rows(row.get("panels")),
                "evidence_refs": ["research_plan/figure_storyboard.json"],
            }
        )
    return result


def _table_rows(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    storyboard = contracts.get("figure_storyboard") or {}
    rows = _rows(storyboard.get("tables"))
    return [
        {
            "table_id": _text(row.get("table_id") or row.get("id") or f"table-{index}"),
            "title": _pick(row, "proposed_title", locale="en") or _pick(row, "title", locale="en"),
            "title_zh": _pick(row, "proposed_title", locale="zh-CN") or _pick(row, "title", locale="zh-CN"),
            "purpose": _pick(row, "expected_content", locale="en") or _pick(row, "purpose", locale="en"),
            "purpose_zh": _pick(row, "expected_content", locale="zh-CN") or _pick(row, "purpose", locale="zh-CN"),
            "evidence_refs": ["research_plan/figure_storyboard.json"],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _method_rows(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    method_plan = contracts.get("method_plan") or {}
    rows = _rows(method_plan.get("method_tasks"))
    return [
        {
            "task_id": _text(row.get("task_id") or row.get("id") or f"method-{index}"),
            "method": _pick(row, "method_family", locale="en") or _pick(row, "method", locale="en"),
            "method_zh": _pick(row, "method_family", locale="zh-CN") or _pick(row, "method", locale="zh-CN"),
            "validation": _pick(row, "validation_metric", locale="en")
            or _pick(row, "validation_design", locale="en"),
            "validation_zh": _pick(row, "validation_metric", locale="zh-CN")
            or _pick(row, "validation_design", locale="zh-CN"),
            "required_data": list(row.get("required_data") or row.get("required_data_roles") or []),
            "evidence_refs": ["research_plan/method_plan.json"],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _data_roles(figures: Iterable[Mapping[str, Any]], methods: Iterable[Mapping[str, Any]]) -> list[str]:
    values: set[str] = set()
    for row in [*figures, *methods]:
        for item in row.get("required_data") or []:
            text = _text(item, limit=160)
            if text:
                values.add(text)
    return sorted(values)


def _statistics_summary(contracts: Mapping[str, Any]) -> dict[str, Any]:
    contract = contracts.get("statistical_validation_contract") or {}
    values: list[str] = []
    for key in (
        "validation_design",
        "validation_designs",
        "primary_metric",
        "metrics",
        "uncertainty_method",
        "uncertainty_methods",
        "threshold_policy",
        "threshold_source",
    ):
        value = contract.get(key)
        rendered = _join(value, locale="en")
        if rendered:
            values.append(rendered)
    return {
        "summary": "; ".join(dict.fromkeys(values)) or "Structured statistical validation contract",
        "summary_zh": "；".join(dict.fromkeys(values)) or "已登记的统计验证合同",
        "evidence_refs": ["research_plan/statistical_validation_contract.json"],
    }


def build_research_plan_decision_brief(
    *,
    project_metadata: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
    semantic_delta: Mapping[str, Any],
    limitations: Iterable[str],
    pre_execution_decision: str,
    review_rule_decision: str,
    presentation_contracts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, complete decision brief from semantic and display contracts.

    The scientific fingerprint intentionally removes localized presentation
    fields so translation-only edits do not create a new scientific decision.
    The author-facing packet must nevertheless render those fields when the
    raw structured contracts are available.
    """

    subject = fingerprint.get("scientific_plan_subject") or {}
    semantic_contracts = subject.get("contracts") if isinstance(subject, Mapping) else {}
    semantic_contracts = semantic_contracts if isinstance(semantic_contracts, Mapping) else {}
    contracts = presentation_contracts if isinstance(presentation_contracts, Mapping) else semantic_contracts
    blueprint = contracts.get("research_blueprint") or {}
    objective = blueprint.get("research_objective") if isinstance(blueprint, Mapping) else {}
    objective = objective if isinstance(objective, Mapping) else {}
    claims = _claim_rows(contracts)
    figures = _figure_rows(contracts)
    tables = _table_rows(contracts)
    methods = _method_rows(contracts)
    title = (
        _text(objective.get("working_title"))
        or _text(project_metadata.get("title"))
        or _text(project_metadata.get("idea"))
        or "Research plan"
    )
    title_zh = _text(objective.get("working_title_zh_cn")) or title
    objective_en = _text(objective.get("scientific_objective")) or _text(project_metadata.get("idea"))
    objective_zh = _text(objective.get("scientific_objective_zh_cn")) or objective_en
    limitations_list = sorted({str(item).strip() for item in limitations if str(item).strip()})
    facts: list[dict[str, Any]] = [
        {
            "fact_id": "research-objective",
            "fact_type": "objective",
            "label_zh": "研究目标",
            "label_en": "Research objective",
            "value_zh": objective_zh,
            "value_en": objective_en,
            "evidence_refs": ["research_plan/research_blueprint.json"],
        },
        {
            "fact_id": "pre-execution-decision",
            "fact_type": "feasibility",
            "label_zh": "执行前可行性",
            "label_en": "Pre-execution feasibility",
            "value_zh": pre_execution_decision,
            "value_en": pre_execution_decision,
            "evidence_refs": ["research_plan/pre_execution_support_report.json"],
        },
        {
            "fact_id": "review-rule-decision",
            "fact_type": "statistical_review",
            "label_zh": "统计审查覆盖",
            "label_en": "Statistical review coverage",
            "value_zh": review_rule_decision,
            "value_en": review_rule_decision,
            "evidence_refs": ["research_plan/review_rule_coverage_report.json"],
        },
    ]
    for row in claims:
        facts.append(
            {
                "fact_id": f"claim:{row['claim_id']}",
                "fact_type": "claim",
                "label_zh": row["claim_id"],
                "label_en": row["claim_id"],
                "value_zh": row["research_question_zh"],
                "value_en": row["research_question"],
                "evidence_refs": row["evidence_refs"],
            }
        )
    for row in figures:
        facts.append(
            {
                "fact_id": f"figure:{row['figure_id']}",
                "fact_type": "figure",
                "label_zh": row["title_zh"] or row["figure_id"],
                "label_en": row["title"] or row["figure_id"],
                "value_zh": row["expected_zh"],
                "value_en": row["expected"],
                "evidence_refs": row["evidence_refs"],
            }
        )
    semantic_subject = {
        "scientific_plan_subject": fingerprint.get("scientific_plan_subject") or {},
        "claim_ids": [row["claim_id"] for row in claims],
        "figure_ids": [row["figure_id"] for row in figures],
        "table_ids": [row["table_id"] for row in tables],
    }
    brief = {
        "schema_version": RESEARCH_PLAN_BRIEF_SCHEMA,
        "decision_family": "scientific_plan",
        "title": title,
        "title_zh": title_zh,
        "decision_question_zh": "是否确认以下完整研究蓝图、可行性边界、统计设计和主图合同，以进入关键图表执行？",
        "decision_question_en": "Do you approve this complete research blueprint, feasibility boundary, statistical design, and figure contract for key-figure execution?",
        "summary_zh": "本页汇总本轮研究计划的具体科学内容；确认后，Agent 只能修复实现，不能自行改变数据角色、方法、统计或主图语义。",
        "summary_en": "This page summarizes the complete scientific plan. After confirmation, agents may repair implementation but may not change data roles, methods, statistics, or figure semantics.",
        "objective_zh": objective_zh,
        "objective_en": objective_en,
        "research_questions": claims,
        "claims": claims,
        "figures": figures,
        "tables": tables,
        "data_roles": _data_roles(figures, methods),
        "methods": methods,
        "statistics": _statistics_summary(contracts),
        "limitations": limitations_list,
        "pre_execution_decision": pre_execution_decision,
        "review_rule_decision": review_rule_decision,
        "semantic_delta": dict(semantic_delta),
        "facts": facts,
        "reopen_conditions_zh": "研究问题、claim 边界、数据角色、cohort、样本单位、方法、统计设计、主图或 panel 语义变化时必须重新确认。",
        "reopen_conditions_en": "Changes to the research question, claim boundary, data role, cohort, sample unit, method, statistics, or main-figure/panel semantics require a new confirmation.",
        "not_confirming_zh": "本次不确认 HTML 样式、翻译措辞、JSON 排序、绝对路径、审计清单或其它派生产物。",
        "not_confirming_en": "This decision does not approve HTML styling, translation wording, JSON ordering, absolute paths, audit inventories, or other derived artifacts.",
        "semantic_subject": semantic_subject,
    }
    brief["brief_semantic_sha256"] = _hash(
        {
            "schema_version": RESEARCH_PLAN_BRIEF_SCHEMA,
            "decision_family": brief["decision_family"],
            "semantic_subject": semantic_subject,
            "decision_question": "scientific_plan_confirmation",
        }
    )
    return brief


def validate_research_plan_decision_brief(brief: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if brief.get("schema_version") != RESEARCH_PLAN_BRIEF_SCHEMA:
        issues.append("unsupported_research_plan_brief_schema")
    if not _text(brief.get("decision_question_zh")):
        issues.append("missing_decision_question")
    if not _text(brief.get("objective_zh")) and not _text(brief.get("objective_en")):
        issues.append("missing_research_objective")
    if not isinstance(brief.get("claims"), list) or not brief.get("claims"):
        issues.append("missing_claims")
    if not isinstance(brief.get("figures"), list):
        issues.append("missing_figure_contracts")
    if not brief.get("brief_semantic_sha256"):
        issues.append("missing_brief_semantic_sha256")
    for fact in brief.get("facts") or []:
        if not isinstance(fact, Mapping) or not fact.get("evidence_refs"):
            issues.append("fact_without_evidence_refs")
            break
    return issues


def _link(root: Path, output_dir: Path, relative: str, label: str) -> str:
    target = root / relative
    if not target.exists():
        return escape(label)
    href = os.path.relpath(target, output_dir).replace("\\", "/")
    return f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'


def _cell(value: Any) -> str:
    return escape(_text(value, limit=800)).replace("\n", "<br>")


def render_research_plan_decision_html(
    root: str | Path,
    output_dir: str | Path,
    brief: Mapping[str, Any],
    *,
    locale: str,
) -> str:
    """Render one readable, evidence-bound page from the same structured brief."""

    project_root = Path(root)
    packet_dir = Path(output_dir)
    zh = locale == "zh-CN"
    title = _text(brief.get("title_zh" if zh else "title")) or "Research plan"
    summary = _text(brief.get("summary_zh" if zh else "summary_en"))
    question = _text(brief.get("decision_question_zh" if zh else "decision_question_en"))
    objective = _text(brief.get("objective_zh" if zh else "objective_en"))
    changed = (brief.get("semantic_delta") or {}).get("classification") != "no_scientific_change"
    delta = _text((brief.get("semantic_delta") or {}).get("summary_zh" if zh else "summary_en"))
    headings = (
        {
            "decision": "本次确认",
            "objective": "研究目标与问题",
            "claims": "可主张结论与边界",
            "figures": "主图与表格合同",
            "methods": "数据、方法与统计设计",
            "limitations": "可行性、限制与待处理事项",
            "delta": "相对上次确认的语义变化",
            "meaning": "确认含义与重新打开条件",
            "files": "完整文件与技术附件",
            "claim": "主张",
            "question_col": "研究问题",
            "expected": "计划支持",
            "boundary": "不能外推",
            "figure": "图表",
            "data": "数据角色",
            "method": "方法任务",
            "validation": "验证/统计",
            "none": "无",
        }
        if zh
        else {
            "decision": "Decision",
            "objective": "Research objective and questions",
            "claims": "Claims and boundaries",
            "figures": "Figure and table contracts",
            "methods": "Data, methods, and statistics",
            "limitations": "Feasibility, limitations, and pending items",
            "delta": "Semantic delta from the prior confirmation",
            "meaning": "Confirmation meaning and reopen conditions",
            "files": "Complete files and technical attachments",
            "claim": "Claim",
            "question_col": "Research question",
            "expected": "Planned support",
            "boundary": "Not supported",
            "figure": "Figure/table",
            "data": "Data roles",
            "method": "Method task",
            "validation": "Validation/statistics",
            "none": "None",
        }
    )
    claim_rows = []
    for row in brief.get("claims") or []:
        claim_rows.append(
            "<tr>"
            f"<td><code>{_cell(row.get('claim_id'))}</code></td>"
            f"<td>{_cell(row.get('research_question_zh' if zh else 'research_question'))}</td>"
            f"<td>{_cell(row.get('expected_finding_zh' if zh else 'expected_finding'))}</td>"
            f"<td>{_cell(row.get('boundary_zh' if zh else 'boundary'))}</td>"
            "</tr>"
        )
    figure_rows = []
    for row in brief.get("figures") or []:
        figure_rows.append(
            "<article class=\"contract\">"
            f"<h3>{_cell(row.get('figure_id'))}: {_cell(row.get('title_zh' if zh else 'title'))}</h3>"
            f"<p><strong>{headings['question_col']}:</strong> {_cell(row.get('question_zh' if zh else 'question'))}</p>"
            f"<p><strong>{headings['expected']}:</strong> {_cell(row.get('expected_zh' if zh else 'expected'))}</p>"
            f"<p class=\"boundary\"><strong>{headings['boundary']}:</strong> {_cell(row.get('boundary_zh' if zh else 'boundary'))}</p>"
            f"<p class=\"muted\"><strong>{headings['data']}:</strong> {_cell(_join(row.get('required_data'), locale=locale))}</p>"
            "</article>"
        )
    table_rows = []
    for row in brief.get("tables") or []:
        table_rows.append(
            "<tr>"
            f"<td><code>{_cell(row.get('table_id'))}</code></td>"
            f"<td>{_cell(row.get('title_zh' if zh else 'title'))}</td>"
            f"<td>{_cell(row.get('purpose_zh' if zh else 'purpose'))}</td>"
            "</tr>"
        )
    method_rows = []
    for row in brief.get("methods") or []:
        method_rows.append(
            "<tr>"
            f"<td><code>{_cell(row.get('task_id'))}</code></td>"
            f"<td>{_cell(row.get('method_zh' if zh else 'method'))}</td>"
            f"<td>{_cell(row.get('validation_zh' if zh else 'validation'))}</td>"
            f"<td>{_cell(_join(row.get('required_data'), locale=locale))}</td>"
            "</tr>"
        )
    limitation_items = [
        f"<li>{_cell(item)}</li>" for item in brief.get("limitations") or []
    ] or [f"<li>{headings['none']}</li>"]
    source_links = [
        _link(project_root, packet_dir, "research_plan/research_plan.zh-CN.md", "中文完整研究方案" if zh else "Chinese research plan"),
        _link(project_root, packet_dir, "research_plan/research_plan.md", "英文完整研究方案" if zh else "English research plan"),
        _link(project_root, packet_dir, "research_plan/statistical_validation_contract.md", "统计验证合同" if zh else "Statistical validation contract"),
        _link(project_root, packet_dir, "research_plan/pre_execution_support_report.html", "执行前支持检查" if zh else "Pre-execution support"),
        # The packet-local audit is written with the HTML package.  Do not
        # check it against the project root while rendering, or the link is
        # silently downgraded to plain text before the package exists.
        f'<a href="stage_audit.json">{escape("技术审计 JSON" if zh else "Technical audit JSON")}</a>',
    ]
    language_link = "stage_summary.en.html" if zh else "stage_summary.zh-CN.html"
    language_label = "English" if zh else "中文"
    return f"""<!doctype html>
<html lang="{escape(locale)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#526176; --paper:#fff; --page:#f4f7fb; --line:#dce5ef; --blue:#0a5eb8; --blue-soft:#eaf3ff; --green:#126b49; --green-soft:#eaf7f0; --amber:#935d00; --amber-soft:#fff5df; --red:#a12929; --red-soft:#fff0f0; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--page); color:var(--ink); font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif; line-height:1.62; }}
    main {{ max-width:1160px; margin:0 auto; padding:28px 20px 52px; }}
    header {{ background:#0b4f91; color:#fff; padding:30px 34px; border-radius:10px; }}
    h1 {{ margin:5px 0 10px; font-size:1.85rem; line-height:1.28; }}
    h2 {{ margin:0 0 13px; font-size:1.28rem; }}
    h3 {{ margin:0 0 8px; font-size:1rem; }}
    section {{ margin-top:18px; background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:24px 27px; }}
    .eyebrow {{ font-size:.82rem; letter-spacing:.08em; opacity:.85; }}
    .status {{ display:inline-block; margin-top:12px; padding:5px 8px; border-radius:5px; background:rgba(255,255,255,.16); font-family:Consolas,monospace; font-size:.82rem; overflow-wrap:anywhere; }}
    .notice {{ padding:13px 15px; border-left:4px solid var(--blue); background:var(--blue-soft); border-radius:5px; }}
    .changed {{ border-left-color:var(--amber); background:var(--amber-soft); }}
    .boundary {{ color:#8c2d2d; }}
    .muted {{ color:var(--muted); }}
    table {{ width:100%; border-collapse:collapse; margin-top:12px; font-size:.92rem; }}
    th, td {{ border:1px solid var(--line); padding:9px 10px; vertical-align:top; text-align:left; }}
    th {{ background:#edf4fb; }}
    .contract {{ border-top:1px solid var(--line); padding:15px 0; }}
    .contract:first-of-type {{ border-top:0; padding-top:0; }}
    code {{ background:#eef2f6; padding:1px 4px; border-radius:3px; overflow-wrap:anywhere; }}
    ul {{ margin:8px 0 0; padding-left:22px; }}
    a {{ color:#075cae; font-weight:600; }}
    .files {{ display:flex; flex-wrap:wrap; gap:10px 16px; }}
    @media (max-width:700px) {{ main {{ padding:14px 10px 36px; }} header {{ padding:23px 20px; }} section {{ padding:19px 16px; }} h1 {{ font-size:1.5rem; }} table {{ font-size:.84rem; }} th,td {{ padding:7px; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">DRAFTPAPER-LOOP · RESEARCH PLAN DECISION</div>
    <h1>{escape(title)}</h1>
    <p>{escape(summary)}</p>
    <span class="status">{escape(str(brief.get('brief_semantic_sha256') or ''))}</span>
    <p><a href="{language_link}" style="color:#fff">{language_label}</a></p>
  </header>
  <section>
    <h2>{headings['decision']}</h2>
    <div class="notice {'changed' if changed else ''}"><strong>{escape(question)}</strong><br>{escape(delta)}</div>
  </section>
  <section>
    <h2>{headings['objective']}</h2>
    <p>{escape(objective)}</p>
  </section>
  <section>
    <h2>{headings['claims']}</h2>
    <table><thead><tr><th>{headings['claim']}</th><th>{headings['question_col']}</th><th>{headings['expected']}</th><th>{headings['boundary']}</th></tr></thead><tbody>{''.join(claim_rows)}</tbody></table>
  </section>
  <section>
    <h2>{headings['figures']}</h2>
    {''.join(figure_rows) or f'<p>{headings["none"]}</p>'}
    <table><thead><tr><th>{headings['figure']}</th><th>{headings['question_col']}</th><th>{headings['expected']}</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table>
  </section>
  <section>
    <h2>{headings['methods']}</h2>
    <p><strong>{headings['data']}:</strong> {escape(_join(brief.get('data_roles'), locale=locale)) or headings['none']}</p>
    <p><strong>{headings['validation']}:</strong> {escape(_text((brief.get('statistics') or {}).get('summary_zh' if zh else 'summary')))}</p>
    <table><thead><tr><th>ID</th><th>{headings['method']}</th><th>{headings['validation']}</th><th>{headings['data']}</th></tr></thead><tbody>{''.join(method_rows)}</tbody></table>
  </section>
  <section>
    <h2>{headings['limitations']}</h2>
    <p><strong>Pre-execution:</strong> {escape(_text(brief.get('pre_execution_decision')))} · <strong>Review rules:</strong> {escape(_text(brief.get('review_rule_decision')))}</p>
    <ul>{''.join(limitation_items)}</ul>
  </section>
  <section>
    <h2>{headings['meaning']}</h2>
    <p>{escape(_text(brief.get('not_confirming_zh' if zh else 'not_confirming_en')))}</p>
    <p>{escape(_text(brief.get('reopen_conditions_zh' if zh else 'reopen_conditions_en')))}</p>
  </section>
  <section>
    <h2>{headings['files']}</h2>
    <div class="files">{' · '.join(source_links)}</div>
  </section>
</main>
</body>
</html>
"""


__all__ = [
    "RESEARCH_PLAN_BRIEF_SCHEMA",
    "build_research_plan_decision_brief",
    "render_research_plan_decision_html",
    "validate_research_plan_decision_brief",
]
