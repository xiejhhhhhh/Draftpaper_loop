"""Core, offline bilingual HTML renderer for literature review artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

from .literature_scoring import identify_legacy_zero_scores

LOCALES = {
    "en": {
        "index_title": "Literature Summary Index",
        "index_heading": "Literature Summary Index",
        "source_counts": "Source counts",
        "workflow_summary": "Literature pipeline summary",
        "discovered_candidates": "Discovered candidates",
        "prefetch_rejected": "Rejected before fetch",
        "identity_resolved": "Identities resolved",
        "identity_ambiguous": "Ambiguous or mismatched identities",
        "fulltext_fetched": "Full texts fetched on demand",
        "postfetch_rejected": "Rejected after fetch",
        "active_references": "Active references",
        "quarantine_records": "Quarantine records",
        "provider_status": "Provider/runtime status",
        "review_required": "Requires review",
        "filter_source": "Filter by source",
        "all": "all",
        "title": "Title",
        "citation_key": "Citation key",
        "source_categories": "Source categories",
        "origin": "Origin",
        "zotero_collection": "Zotero collection",
        "local_locator": "Local locator",
        "file_id": "File ID",
        "metadata": "Metadata",
        "pdf_parser": "PDF/parser",
        "parser_route": "Parser route",
        "candidate_state": "Candidate state",
        "discovery_provider": "Discovery provider",
        "prefetch_topic": "Pre-fetch topic gate",
        "identity_status": "Identity status",
        "identity_checks": "DOI/title/author/year checks",
        "fulltext_decision": "Full-text decision",
        "fetch_runtime": "Paper-fetch result",
        "postfetch_status": "Post-fetch status",
        "citation_eligibility": "Citation eligibility",
        "snapshot_hash": "Snapshot hash",
        "quarantine_heading": "Excluded and quarantined candidates",
        "quarantine_reason": "Exclusion reason",
        "recovery_route": "Recovery route",
        "code_sources": "GitHub/Zenodo code sources",
        "context": "Context",
        "search_context": "Search context",
        "search_query": "Search query",
        "query_id": "Query ID",
        "combination": "Combination",
        "retention": "Retention",
        "citation_weight": "Citation weight",
        "relevance": "Relevance",
        "journal_authority": "Journal authority",
        "source_records": "Source records",
        "field_provenance": "Field provenance",
        "parse_receipts": "Document parse receipts",
        "query_provenance": "Query provenance",
        "recommended_section": "Recommended section",
        "abstract": "Abstract Summary",
        "reading_notes": "Structured Reading Notes",
        "read_status": "Read Status",
        "research_question": "Research Question",
        "data_used": "Data Used",
        "methods": "Methods",
        "scientific_results": "Scientific Results",
        "limitations": "Limitations",
        "relevance_to_study": "Relevance to Study",
        "pdf_excerpt": "PDF Quick-Read Excerpt",
        "verified_teaching_analysis": "Evidence-verified teaching analysis",
        "one_sentence": "Core contribution in one sentence",
        "validation": "Validation and uncertainty checks",
        "contribution": "What this paper contributes",
        "evidence_mapping": "Field-level evidence mapping",
        "paper_report": "Paper-reported fact or evidence-grounded paper synthesis",
        "project_synthesis": "Project-level synthesis; not presented as a paper fact",
        "reading_order": "Recommended reading order",
        "citation_role": "Project citation role",
        "prerequisites": "Read after",
        "evidence_status": "Teaching evidence status",
        "transfer_boundary": "Transfer boundary",
        "formal_learning_portal": "Open the linked learning portal",
        "not_available": "n/a",
        "not_evaluated": "not evaluated",
        "language_zh": "中文",
        "language_en": "English",
    },
    "zh-CN": {
        "index_title": "文献摘要索引",
        "index_heading": "文献摘要索引",
        "source_counts": "来源统计",
        "workflow_summary": "文献处理流程摘要",
        "discovered_candidates": "发现候选数",
        "prefetch_rejected": "抓取前拒绝数",
        "identity_resolved": "已完成身份解析数",
        "identity_ambiguous": "身份歧义或不一致数",
        "fulltext_fetched": "按需抓取全文数",
        "postfetch_rejected": "抓取后拒绝数",
        "active_references": "活动文献数",
        "quarantine_records": "隔离记录数",
        "provider_status": "Provider/运行时状态",
        "review_required": "是否需要人工复核",
        "filter_source": "按来源筛选",
        "all": "全部",
        "title": "标题",
        "citation_key": "引用键",
        "source_categories": "来源类别",
        "origin": "记录来源",
        "zotero_collection": "Zotero 分类",
        "local_locator": "本地定位",
        "file_id": "文件 ID",
        "metadata": "元数据",
        "pdf_parser": "PDF/解析器",
        "parser_route": "解析路线",
        "candidate_state": "候选状态",
        "discovery_provider": "发现来源",
        "prefetch_topic": "抓取前主题门禁",
        "identity_status": "身份解析状态",
        "identity_checks": "DOI/标题/作者/年份核验",
        "fulltext_decision": "全文抓取决策",
        "fetch_runtime": "Paper-fetch 结果",
        "postfetch_status": "抓取后复核状态",
        "citation_eligibility": "引用资格",
        "snapshot_hash": "快照哈希",
        "quarantine_heading": "已排除及隔离候选",
        "quarantine_reason": "排除原因",
        "recovery_route": "恢复路线",
        "code_sources": "GitHub/Zenodo 代码来源",
        "context": "用途上下文",
        "search_context": "检索上下文",
        "search_query": "检索式",
        "query_id": "检索 ID",
        "combination": "组合级别",
        "retention": "保留策略",
        "citation_weight": "引用权重",
        "relevance": "相关性",
        "journal_authority": "期刊权威性",
        "source_records": "来源记录",
        "field_provenance": "字段来源",
        "parse_receipts": "文献解析收据",
        "query_provenance": "检索溯源",
        "recommended_section": "建议使用章节",
        "abstract": "摘要概览",
        "reading_notes": "结构化阅读笔记",
        "read_status": "阅读状态",
        "research_question": "研究问题",
        "data_used": "使用数据",
        "methods": "方法",
        "scientific_results": "科学结果",
        "limitations": "局限性",
        "relevance_to_study": "与当前研究的相关性",
        "pdf_excerpt": "PDF 快速阅读摘录",
        "verified_teaching_analysis": "证据核验后的教学解读",
        "one_sentence": "一句话核心贡献",
        "validation": "验证设计与不确定性检查",
        "contribution": "该文献的具体贡献",
        "evidence_mapping": "字段级证据映射",
        "paper_report": "论文原文事实或有证据约束的论文综合",
        "project_synthesis": "项目层综合判断；不作为论文原文事实展示",
        "reading_order": "建议阅读顺序",
        "citation_role": "项目中的引用角色",
        "prerequisites": "建议先理解",
        "evidence_status": "教学证据状态",
        "transfer_boundary": "迁移边界",
        "formal_learning_portal": "打开关联学习门户",
        "not_available": "不适用",
        "not_evaluated": "尚未评估",
        "language_zh": "中文",
        "language_en": "English",
    },
}


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")


def _read_snapshot_hash(references_dir: Path) -> str:
    path = references_dir / "literature_snapshot.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    return str(payload.get("snapshot_hash") or "") if isinstance(payload, dict) else ""


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _enrichment_hash(payload: Mapping[str, Any]) -> str:
    material = json.dumps(
        {str(key): value for key, value in payload.items() if str(key) != "enrichment_hash"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _valid_verified_analysis(analysis: Mapping[str, Any]) -> bool:
    required = {
        "one_sentence",
        "research_question",
        "data",
        "method",
        "validation",
        "result",
        "limitation",
        "contribution",
        "relation_to_project",
        "transfer_boundary",
    }
    if not required.issubset(analysis):
        return False
    for field in required:
        item = analysis.get(field)
        if (
            not isinstance(item, Mapping)
            or not str(item.get("zh-CN") or "").strip()
            or not str(item.get("en") or "").strip()
            or not [value for value in item.get("source_ids") or () if str(value)]
            or not isinstance(item.get("evidence_quotes"), list)
            or not item.get("evidence_quotes")
        ):
            return False
        scope = str(item.get("statement_scope") or "")
        if field in {"relation_to_project", "transfer_boundary"}:
            if scope != "project_synthesis":
                return False
        elif scope not in {"paper_report", "paper_synthesis"}:
            return False
    return True


def _load_verified_teaching_enrichment(
    references_dir: Path,
    corpus_manifest: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return the optional Guidance projection only when it covers this corpus.

    Core retains ownership of its summary pages.  The optional sidecar may
    enrich their reader-facing explanation only after all accepted works have
    verifier-promoted analyses tied to the exact same corpus hash.
    """

    corpus_hash = str(corpus_manifest.get("corpus_snapshot_hash") or "")
    accepted = {
        str(item.get("citation_key") or "")
        for item in corpus_manifest.get("accepted_works") or ()
        if isinstance(item, Mapping) and str(item.get("citation_key") or "")
    }
    path = references_dir.parent / "guidance" / "learning" / "literature" / "core_summary_enrichment.json"
    payload = _read_json_object(path)
    if (
        payload.get("schema_version") != "dpl.literature_summary_enrichment.v1"
        or str(payload.get("enrichment_hash") or "") != _enrichment_hash(payload)
        or str(payload.get("core_corpus_snapshot_hash") or "") != corpus_hash
        or int(payload.get("accepted_work_count") or 0) != len(accepted)
        or int(payload.get("verified_analysis_count") or 0) != len(accepted)
    ):
        return {}
    papers = [item for item in payload.get("papers") or () if isinstance(item, Mapping)]
    by_key = {str(item.get("citation_key") or ""): dict(item) for item in papers if str(item.get("citation_key") or "")}
    if set(by_key) != accepted:
        return {}
    if any(
        not isinstance(item.get("analysis"), Mapping)
        or not _valid_verified_analysis(item["analysis"])
        for item in by_key.values()
    ):
        return {}
    return by_key


def _localized_teaching_value(value: Any) -> str:
    if not isinstance(value, Mapping):
        return f"<p>{escape(str(value or ''))}</p>"
    en = str(value.get("en") or value.get("zh-CN") or "")
    zh = str(value.get("zh-CN") or value.get("en") or "")
    return f'<p data-dpl-localized="true" data-dpl-en="{escape(en, quote=True)}" data-dpl-zh="{escape(zh, quote=True)}">{escape(en)}</p>'


def _teaching_evidence_mapping_html(
    analysis: Mapping[str, Any],
    locale: Mapping[str, str],
) -> str:
    """Render short, readable supporting excerpts instead of orphaned hashes."""

    rows: list[str] = []
    for field, item in analysis.items():
        if not isinstance(item, Mapping):
            continue
        supports = item.get("evidence_quotes") or ()
        if not isinstance(supports, list) or not supports:
            continue
        scope = str(item.get("statement_scope") or "paper_report")
        scope_label = locale.get(scope, scope.replace("_", " "))
        quotes = [
            str(support.get("quote") or "").strip()
            for support in supports
            if isinstance(support, Mapping) and str(support.get("quote") or "").strip()
        ]
        if not quotes:
            continue
        rows.append(
            "<li>"
            f"<strong>{escape(locale.get(field, field.replace('_', ' ')))}</strong> · {escape(scope_label)}"
            + "".join(f"<blockquote>{escape(quote)}</blockquote>" for quote in quotes)
            + "</li>"
        )
    if not rows:
        return ""
    return (
        f'<details class="teaching-evidence"><summary data-i18n="evidence_mapping">'
        f'{escape(locale["evidence_mapping"])}</summary><ul>{"".join(rows)}</ul></details>'
    )


def _pipeline_summary(references_dir: Path, active_count: int) -> dict[str, Any]:
    prefetch = _read_json_object(references_dir / "prefetch_relevance_report.json")
    identity = _read_json_object(references_dir / "paper_identity_resolution_summary.json")
    fetch = _read_json_object(references_dir / "paper_fetch_manifest.json")
    postfetch = _read_json_object(references_dir / "postfetch_relevance_report.json")
    quarantine = _read_json_object(references_dir / "quarantined_literature_candidates.json")
    identity_status = identity.get("status_counts") if isinstance(identity.get("status_counts"), dict) else {}
    postfetch_status = postfetch.get("status_counts") if isinstance(postfetch.get("status_counts"), dict) else {}
    review_count = int(postfetch_status.get("review_required") or 0) + int(identity_status.get("ambiguous") or 0)
    return {
        "discovered_candidates": int(prefetch.get("candidate_count") or active_count),
        "prefetch_rejected": int(prefetch.get("rejected_count") or 0),
        "identity_resolved": int(identity.get("resolved_count") or 0),
        "identity_ambiguous": sum(int(identity_status.get(value) or 0) for value in ("ambiguous", "mismatch")),
        "fulltext_fetched": int(fetch.get("success_count") or 0),
        "postfetch_rejected": sum(int(count or 0) for status, count in postfetch_status.items() if str(status).startswith("rejected_")),
        "active_references": active_count,
        "quarantine_records": int(quarantine.get("count") or 0),
        "provider_status": f"{fetch.get('status') or 'not_run'} / {fetch.get('runtime_source') or 'n/a'}",
        "review_required": "yes" if review_count else "no",
    }


def _pipeline_summary_html(summary: dict[str, Any]) -> str:
    keys = (
        "discovered_candidates",
        "prefetch_rejected",
        "identity_resolved",
        "identity_ambiguous",
        "fulltext_fetched",
        "postfetch_rejected",
        "active_references",
        "quarantine_records",
        "provider_status",
        "review_required",
    )
    rows = "".join(
        f'<div><dt data-i18n="{key}">{escape(LOCALES["en"][key])}</dt><dd>{escape(str(summary.get(key, "n/a")))}</dd></div>' for key in keys
    )
    return f'<section aria-labelledby="pipeline-summary"><h2 id="pipeline-summary" data-i18n="workflow_summary">{LOCALES["en"]["workflow_summary"]}</h2><dl class="pipeline-summary">{rows}</dl></section>'


def _quarantine_html(references_dir: Path) -> str:
    payload = _read_json_object(references_dir / "quarantined_literature_candidates.json")
    rows: list[str] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        assessment = item.get("postfetch_relevance") if isinstance(item.get("postfetch_relevance"), dict) else {}
        reasons = item.get("rejection_codes") or assessment.get("reason_codes") or []
        recovery = str((item.get("quarantine_artifact") or {}).get("rollback_route") or "correct identity/topic evidence and rerun search")
        rows.append(
            "<li>"
            f"<strong>{escape(str(item.get('title') or 'n/a'))}</strong>; "
            f'<span data-i18n="postfetch_status">{escape(LOCALES["en"]["postfetch_status"])}</span>: '
            f"{escape(str(item.get('postfetch_state') or item.get('candidate_state') or 'rejected'))}; "
            f'<span data-i18n="quarantine_reason">{escape(LOCALES["en"]["quarantine_reason"])}</span>: '
            f"{escape(', '.join(str(value) for value in reasons) or 'n/a')}; "
            f'<span data-i18n="recovery_route">{escape(LOCALES["en"]["recovery_route"])}</span>: {escape(recovery)}'
            "</li>"
        )
    if not rows:
        return ""
    return f'<section><h2 data-i18n="quarantine_heading">{LOCALES["en"]["quarantine_heading"]}</h2><ul>{"".join(rows)}</ul></section>'


def _safe_filename(text: str, fallback: str) -> str:
    import re

    name = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return name[:70].strip("_") or fallback


def _score_display(item: dict[str, Any], field: str) -> str:
    if field in identify_legacy_zero_scores(item):
        return "legacy zero ambiguous"
    value = item.get(field)
    if value is None or value == "":
        status = str((item.get("score_status") or {}).get(field) or "not_evaluated")
        return status.replace("_", " ")
    return str(value)


def _link_html(item: dict[str, Any]) -> str:
    links: list[str] = []
    doi = str(item.get("doi") or "").strip()
    url = str(item.get("url") or "").strip()
    if doi:
        doi_url = doi if doi.startswith(("http://", "https://")) else f"https://doi.org/{doi}"
        links.append(f'<a href="{escape(doi_url)}" target="_blank" rel="noopener">DOI: {escape(doi)}</a>')
    if url:
        links.append(f'<a href="{escape(url)}" target="_blank" rel="noopener">URL</a>')
    return " ".join(links) or "n/a"


def _source_categories(item: dict[str, Any]) -> list[str]:
    aliases = {
        "existing_zotero": "zotero",
        "zotero_collection": "zotero",
        "local_folder": "local_import",
        "supplemental_external": "online_search",
        "semantic_scholar": "online_search",
        "arxiv": "online_search",
        "crossref": "online_search",
        "openalex": "online_search",
        "pubmed": "online_search",
        "europe_pmc": "online_search",
        "dblp": "online_search",
        "nasa_ads": "online_search",
    }
    values: list[str] = []
    for record in item.get("source_records") or []:
        if isinstance(record, dict):
            raw_provider = str(record.get("provider") or "").strip()
            raw = str(record.get("source_type") or raw_provider or "unknown")
            value = aliases.get(raw, raw)
            if value and value not in values:
                values.append(value)
            if raw_provider and raw_provider not in {"online_search", "local_import", "zotero", value} and raw_provider not in values:
                values.append(raw_provider)
    for raw in (item.get("source_type"), item.get("source")):
        value = aliases.get(str(raw or ""), str(raw or ""))
        if value and value not in values:
            values.append(value)
    return values or ["unknown"]


def _load_code_source_records(references_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load metadata-only code leads without making them part of literature truth."""
    path = references_dir / "code_sources.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = payload.get("records") if isinstance(payload, dict) else None
    by_work: dict[str, list[dict[str, Any]]] = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        work_id = str(record.get("work_id") or record.get("literature_work_id") or "").strip()
        if work_id:
            by_work.setdefault(work_id, []).append(record)
    return by_work


def _code_source_summary(item: dict[str, Any], by_work: dict[str, list[dict[str, Any]]]) -> str:
    work_id = str(item.get("work_id") or item.get("canonical_work_id") or "").strip()
    records = by_work.get(work_id, [])
    values = []
    for record in records:
        source_type = str(record.get("source_type") or "code_source")
        version = record.get("version") or record.get("record_id") or "metadata-only"
        status = record.get("selection_status") or "candidate"
        values.append(f"{source_type}:{version} ({status})")
    return "; ".join(values) or "none"


def _source_record_table(item: dict[str, Any], locale: dict[str, str]) -> str:
    rows = []
    for record in item.get("source_records") or []:
        if not isinstance(record, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(record.get('source_type') or 'unknown'))}</td>"
            f"<td>{escape(str(record.get('provider') or record.get('collection') or 'n/a'))}</td>"
            f"<td>{escape(str(record.get('logical_locator') or record.get('file_id') or 'n/a'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Source type</th><th>Provider/collection</th><th>Locator</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else f"<p>{escape(locale['not_available'])}</p>"
    )


def _script(locale_payload: dict[str, dict[str, str]]) -> str:
    return f"""<script>
const DPL_LOCALES = {_json_for_script(locale_payload)};
function dplLocale() {{
  const query = new URLSearchParams(window.location.search).get('lang');
  if (query === 'zh-CN' || query === 'en') return query;
  try {{ const saved = window.localStorage.getItem('draftpaper-locale'); if (saved === 'zh-CN' || saved === 'en') return saved; }} catch (error) {{}}
  return (navigator.language || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}}
function setDplLocale(locale) {{
  const chosen = locale === 'zh-CN' ? 'zh-CN' : 'en';
  const dictionary = DPL_LOCALES[chosen];
  document.documentElement.lang = chosen;
  document.querySelectorAll('[data-i18n]').forEach((node) => {{
    const key = node.dataset.i18n;
    if (dictionary[key]) node.textContent = dictionary[key];
  }});
  document.querySelectorAll('[data-dpl-localized="true"]').forEach((node) => {{
    node.textContent = chosen === 'zh-CN' ? (node.dataset.dplZh || node.dataset.dplEn || '') : (node.dataset.dplEn || node.dataset.dplZh || '');
  }});
  document.querySelectorAll('[data-locale-button]').forEach((node) => {{
    node.setAttribute('aria-pressed', node.dataset.localeButton === chosen ? 'true' : 'false');
  }});
  try {{ window.localStorage.setItem('draftpaper-locale', chosen); }} catch (error) {{}}
}}
function initDplLocale() {{ setDplLocale(dplLocale()); }}
document.addEventListener('DOMContentLoaded', initDplLocale);
</script>"""


def _language_switcher() -> str:
    return """<nav class="language-switcher" aria-label="Language"><button type="button" data-locale-button="zh-CN" aria-pressed="false" onclick="setDplLocale('zh-CN')">中文</button><span aria-hidden="true"> | </span><button type="button" data-locale-button="en" aria-pressed="false" onclick="setDplLocale('en')">English</button></nav>"""


def _style() -> str:
    return """<style>
body { font-family: Arial, sans-serif; max-width: 1180px; margin: 28px auto; padding: 0 18px; line-height: 1.55; color: #202124; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #d9dce1; padding: 7px 8px; text-align: left; vertical-align: top; }
th { background: #f4f6f8; }
.score { font-weight: 600; }
.toolbar { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.pipeline-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); border-top: 1px solid #d9dce1; border-left: 1px solid #d9dce1; }
.pipeline-summary div { min-width: 0; padding: 8px 10px; border-right: 1px solid #d9dce1; border-bottom: 1px solid #d9dce1; }
.pipeline-summary dt { font-weight: 600; }
.pipeline-summary dd { margin: 2px 0 0; overflow-wrap: anywhere; }
.language-switcher { margin: 8px 0 20px; }
.language-switcher button { border: 0; background: transparent; padding: 3px 4px; cursor: pointer; color: #1257a6; }
.language-switcher button[aria-pressed="true"] { font-weight: 700; text-decoration: underline; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>"""


def _detail_html(
    item: dict[str, Any],
    filename: str,
    locale_payload: dict[str, dict[str, str]],
    code_sources_by_work: dict[str, list[dict[str, Any]]],
    snapshot_hash: str = "",
    corpus_hash: str = "",
) -> str:
    locale = locale_payload["en"]
    summary = item.get("deep_summary") or {}
    enrichment = item.get("teaching_enrichment")
    enrichment = enrichment if isinstance(enrichment, Mapping) else {}
    analysis = enrichment.get("analysis") if isinstance(enrichment.get("analysis"), Mapping) else {}
    categories = _source_categories(item)
    parse_receipts = json.dumps(item.get("document_parses") or [], ensure_ascii=False, sort_keys=True, indent=2)
    field_provenance = json.dumps(item.get("field_provenance") or {}, ensure_ascii=False, sort_keys=True, indent=2)
    query_provenance = json.dumps(item.get("query_provenance") or [], ensure_ascii=False, sort_keys=True, indent=2)
    rows = [
        ("citation_key", str(item.get("bibtex_key") or "")),
        ("source_categories", ", ".join(categories)),
        ("origin", str(item.get("reference_origin") or "external_search")),
        ("zotero_collection", str(item.get("zotero_collection") or "n/a")),
        ("local_locator", str(item.get("local_logical_path") or "n/a")),
        ("file_id", str(item.get("local_file_id") or "n/a")),
        ("metadata", str(item.get("metadata_status") or "unknown")),
        ("pdf_parser", str(item.get("pdf_read_status") or "not_parsed")),
        (
            "parser_route",
            str((item.get("document_parses") or [{}])[0].get("route") or "n/a")
            if isinstance((item.get("document_parses") or [{}])[0], dict)
            else "n/a",
        ),
        ("candidate_state", str(item.get("candidate_state") or "unknown")),
        ("discovery_provider", str(item.get("source_provider") or item.get("source") or "unknown")),
        ("prefetch_topic", f"{item.get('topic_relevance_score', 'n/a')} / {item.get('gate_state') or 'n/a'}"),
        ("identity_status", str(item.get("identity_resolution_status") or "legacy_not_resolved")),
        (
            "identity_checks",
            json.dumps((item.get("identity_resolution_receipt") or {}).get("checks") or {}, ensure_ascii=False, sort_keys=True),
        ),
        ("fulltext_decision", str((item.get("fulltext_fetch_decision") or {}).get("reason") or "not_recorded")),
        ("fetch_runtime", str(item.get("paper_fetch_status") or "not_fetched")),
        ("postfetch_status", str(item.get("postfetch_state") or "legacy_active")),
        ("citation_eligibility", str(item.get("citation_eligibility") or "legacy_review_required")),
        ("snapshot_hash", snapshot_hash or "n/a"),
        ("code_sources", _code_source_summary(item, code_sources_by_work)),
        ("search_context", ", ".join(item.get("search_contexts") or [item.get("search_context") or "idea"])),
        ("search_query", "; ".join(item.get("search_queries") or [item.get("search_query") or ""])),
        ("query_id", str(item.get("search_query_id") or "n/a")),
        ("combination", str(item.get("combination_level") or "n/a")),
        ("retention", str(item.get("selection_policy") or "ranked_by_relevance_and_authority")),
        ("citation_weight", _score_display(item, "citation_weight")),
        ("relevance", _score_display(item, "relevance_score")),
        ("journal_authority", _score_display(item, "journal_score")),
        ("reading_order", str(enrichment.get("reading_order") or "n/a")),
        ("citation_role", ", ".join(str(value) for value in enrichment.get("citation_roles") or ())),
        ("prerequisites", ", ".join(str(value) for value in enrichment.get("prerequisites") or ())),
        ("evidence_status", str(enrichment.get("evidence_status") or "not_verified")),
        ("relevance_to_study", str(summary.get("relevance_to_study") or "")),
    ]
    table_rows = "".join(
        f'<tr><th data-i18n="{escape(key)}">{escape(locale.get(key, key))}</th><td>{escape(value)}</td></tr>' for key, value in rows
    )
    # Once every work in the confirmed corpus has a verified Guidance
    # enrichment, do not keep showing older ``deep_summary`` template text in
    # the same reader-facing section.  The raw Core metadata remains above;
    # the teaching interpretation is wholly derived from the promoted fields.
    if analysis:
        sections: list[tuple[str, Any]] = [
            ("abstract", item.get("abstract") or "No abstract metadata is available."),
            ("one_sentence", analysis.get("one_sentence") or ""),
            ("research_question", analysis.get("research_question") or ""),
            ("data_used", analysis.get("data") or ""),
            ("methods", analysis.get("method") or ""),
            ("validation", analysis.get("validation") or ""),
            ("scientific_results", analysis.get("result") or ""),
            ("limitations", analysis.get("limitation") or ""),
            ("contribution", analysis.get("contribution") or ""),
            ("relevance_to_study", analysis.get("relation_to_project") or ""),
            ("transfer_boundary", analysis.get("transfer_boundary") or ""),
        ]
    else:
        sections = [
            ("abstract", item.get("abstract") or "No abstract metadata is available."),
            ("read_status", summary.get("read_status") or ""),
            ("research_question", summary.get("research_question") or ""),
            ("data_used", summary.get("data_used") or ""),
            ("methods", summary.get("methods") or ""),
            ("scientific_results", summary.get("scientific_results") or ""),
            ("limitations", summary.get("limitations") or ""),
            ("relevance_to_study", summary.get("relevance_to_study") or ""),
            ("pdf_excerpt", summary.get("pdf_excerpt") or "No readable PDF excerpt was available."),
        ]
    teaching_heading = f'<h2 data-i18n="verified_teaching_analysis">{escape(locale["verified_teaching_analysis"])}</h2>' if analysis else ""
    headings = "".join(
        f'<h2 data-i18n="{escape(key)}">{escape(locale.get(key, key))}</h2>' + _localized_teaching_value(value) for key, value in sections
    )
    evidence_mapping = _teaching_evidence_mapping_html(analysis, locale) if analysis else ""
    snapshot_meta = f'<meta name="draftpaper-snapshot-hash" content="{escape(snapshot_hash, quote=True)}">' if snapshot_hash else ""
    corpus_meta = f'<meta name="draftpaper-teaching-corpus-hash" content="{escape(corpus_hash, quote=True)}">' if corpus_hash else ""
    snapshot_attr = f' data-snapshot-hash="{escape(snapshot_hash, quote=True)}"' if snapshot_hash else ""
    corpus_attr = f' data-teaching-corpus-hash="{escape(corpus_hash, quote=True)}"' if corpus_hash else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">{snapshot_meta}{corpus_meta}<title>{escape(str(item.get("title") or locale["index_title"]))}</title>{_style()}{_script(locale_payload)}</head>
<body{snapshot_attr}{corpus_attr}>{_language_switcher()}<p><a href="index.html">{escape(locale["index_heading"])}</a></p>
<h1>{escape(str(item.get("title") or locale["index_title"]))}</h1>
<table><tbody>{table_rows}</tbody></table>
<h2 data-i18n="source_records">{escape(locale["source_records"])}</h2>{_source_record_table(item, locale)}
<h2 data-i18n="query_provenance">{escape(locale["query_provenance"])}</h2><pre>{escape(query_provenance)}</pre>
<h2 data-i18n="recommended_section">{escape(locale["recommended_section"])}</h2><p>{escape({"idea": "introduction", "introduction": "introduction", "data": "data", "methods": "methods"}.get(str(item.get("search_context") or "idea"), "introduction"))}</p>
<h2 data-i18n="field_provenance">{escape(locale["field_provenance"])}</h2><pre>{escape(field_provenance)}</pre>
  <h2 data-i18n="parse_receipts">{escape(locale["parse_receipts"])}</h2><pre>{escape(parse_receipts)}</pre>
  {teaching_heading}{headings}{evidence_mapping}
<p>{_link_html(item)}</p>
</body></html>
"""


def render_literature_html(
    references_dir: Path,
    items: list[dict[str, Any]],
    *,
    corpus_manifest: dict[str, Any] | None = None,
) -> list[str]:
    summary_dir = references_dir / "literature_summaries"
    temporary = Path(tempfile.mkdtemp(prefix="literature_summaries.", dir=str(references_dir)))
    try:
        snapshot_hash = _read_snapshot_hash(references_dir)
        corpus_manifest = corpus_manifest or {}
        corpus_hash = str(corpus_manifest.get("corpus_snapshot_hash") or "")
        corpus_status = str(corpus_manifest.get("corpus_status") or "incomplete")
        teaching_enrichment = _load_verified_teaching_enrichment(
            references_dir,
            corpus_manifest,
        )
        pipeline_summary = _pipeline_summary(references_dir, len(items))
        code_sources_by_work = _load_code_source_records(references_dir)
        source_counts: Counter[str] = Counter()
        source_options: set[str] = set()
        index_rows: list[str] = []
        output_files: list[str] = []
        for index, item in enumerate(items, start=1):
            item = dict(item)
            citation_key = str(item.get("bibtex_key") or item.get("citation_key") or "")
            if citation_key in teaching_enrichment:
                item["teaching_enrichment"] = teaching_enrichment[citation_key]
            categories = _source_categories(item)
            source_counts.update(categories)
            source_options.update(categories)
            filename = f"{index:02d}_{_safe_filename(str(item.get('bibtex_key') or ''), 'paper')}.html"
            detail_path = temporary / filename
            detail_path.write_text(
                _detail_html(
                    item,
                    filename,
                    LOCALES,
                    code_sources_by_work,
                    snapshot_hash,
                    corpus_hash,
                ),
                encoding="utf-8",
            )
            output_files.append(f"references/literature_summaries/{filename}")
            score_weight = _score_display(item, "citation_weight")
            relevance = _score_display(item, "relevance_score")
            journal = _score_display(item, "journal_score")
            code_source_summary = _code_source_summary(item, code_sources_by_work)
            enrichment = item.get("teaching_enrichment")
            enrichment = enrichment if isinstance(enrichment, Mapping) else {}
            reading_order = str(enrichment.get("reading_order") or "n/a")
            citation_roles = ", ".join(str(value) for value in enrichment.get("citation_roles") or ()) or "n/a"
            evidence_status = str(enrichment.get("evidence_status") or "not_verified")
            index_rows.append(
                f'<tr data-source-categories="{escape("|".join(categories))}"><td>{index}</td>'
                f'<td><a href="{escape(filename)}">{escape(str(item.get("title") or ""))}</a></td>'
                f"<td>{escape(str(item.get('bibtex_key') or ''))}</td>"
                f"<td>{escape(', '.join(categories))}</td><td>{escape(str(item.get('reference_origin') or 'external_search'))}</td>"
                f"<td>{escape(str(item.get('zotero_collection') or 'n/a'))}</td><td>{escape(str(item.get('local_logical_path') or 'n/a'))}</td>"
                f"<td>{escape(str(item.get('local_file_id') or 'n/a'))}</td><td>{escape(str(item.get('metadata_status') or 'unknown'))}</td>"
                f"<td>{escape(str(item.get('pdf_read_status') or 'not_parsed'))}</td><td>{escape(str((item.get('document_parses') or [{}])[0].get('route') or 'n/a') if isinstance((item.get('document_parses') or [{}])[0], dict) else 'n/a')}</td>"
                f"<td>{escape(str(item.get('candidate_state') or 'unknown'))}</td><td>{escape(code_source_summary)}</td>"
                f"<td>{escape(str(item.get('source_provider') or item.get('source') or 'unknown'))}</td>"
                f"<td>{escape(str(item.get('identity_resolution_status') or 'legacy_not_resolved'))}</td>"
                f"<td>{escape(str((item.get('fulltext_fetch_decision') or {}).get('reason') or 'not_recorded'))}</td>"
                f"<td>{escape(str(item.get('postfetch_state') or 'legacy_active'))}</td>"
                f"<td>{escape(str(item.get('citation_eligibility') or 'legacy_review_required'))}</td>"
                f"<td>{escape(reading_order)}</td><td>{escape(citation_roles)}</td><td>{escape(evidence_status)}</td>"
                f"<td>{escape(', '.join(item.get('search_contexts') or [item.get('search_context') or 'idea']))}</td>"
                f"<td>{escape('; '.join(item.get('search_queries') or [item.get('search_query') or '']))}</td>"
                f"<td>{escape(str(item.get('search_query_id') or 'n/a'))}</td><td>{escape(str(item.get('combination_level') or 'n/a'))}</td>"
                f"<td>{escape(str(item.get('selection_policy') or 'ranked_by_relevance_and_authority'))}</td>"
                f"<td>{escape(score_weight)}</td><td>{escape(relevance)}</td><td>{escape(journal)}</td></tr>"
            )
        source_summary = ", ".join(f"{source}: {count}" for source, count in sorted(source_counts.items())) or "none"
        options = "".join(f'<option value="{escape(source)}">{escape(source)}</option>' for source in sorted(source_options))
        snapshot_meta = f'<meta name="draftpaper-snapshot-hash" content="{escape(snapshot_hash, quote=True)}">' if snapshot_hash else ""
        corpus_meta = f'<meta name="draftpaper-teaching-corpus-hash" content="{escape(corpus_hash, quote=True)}">' if corpus_hash else ""
        snapshot_attr = f' data-snapshot-hash="{escape(snapshot_hash, quote=True)}"' if snapshot_hash else ""
        corpus_attr = f' data-teaching-corpus-hash="{escape(corpus_hash, quote=True)}"' if corpus_hash else ""
        corpus_notice = (
            f'<p data-teaching-corpus-status="{escape(corpus_status, quote=True)}">'
            f"Teaching corpus: {escape(corpus_status)} · {escape(corpus_hash or 'pending confirmation')}</p>"
        )
        learning_portal_link = (
            '<p><a href="../../guidance/learning/site/index.html#chapter/literature_map_and_positioning" '
            'target="_blank" rel="noopener" data-i18n="formal_learning_portal">'
            f"{escape(LOCALES['en']['formal_learning_portal'])}</a></p>"
            if teaching_enrichment
            else ""
        )
        index_html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">{snapshot_meta}{corpus_meta}<title data-i18n="index_title">{LOCALES["en"]["index_title"]}</title>{_style()}{_script(LOCALES)}
<script>function filterSources() {{ const selected = document.getElementById('source-filter').value; document.querySelectorAll('tbody tr[data-source-categories]').forEach((row) => {{ const values = (row.dataset.sourceCategories || '').split('|'); row.style.display = !selected || values.includes(selected) ? '' : 'none'; }}); }}</script>
</head><body{snapshot_attr}{corpus_attr}>{_language_switcher()}<h1 data-i18n="index_heading">{LOCALES["en"]["index_heading"]}</h1>
  {corpus_notice}
  {learning_portal_link}
{_pipeline_summary_html(pipeline_summary)}
<p><span data-i18n="source_counts">{LOCALES["en"]["source_counts"]}</span>: {escape(source_summary)}</p>
<div class="toolbar"><label for="source-filter" data-i18n="filter_source">{LOCALES["en"]["filter_source"]}</label><select id="source-filter" onchange="filterSources()"><option value="" data-i18n="all">{LOCALES["en"]["all"]}</option>{options}</select></div>
  <table><thead><tr>{"".join(f'<th data-i18n="{key}">{LOCALES["en"][key]}</th>' for key in ("title", "citation_key", "source_categories", "origin", "zotero_collection", "local_locator", "file_id", "metadata", "pdf_parser", "parser_route", "candidate_state", "code_sources", "discovery_provider", "identity_status", "fulltext_decision", "postfetch_status", "citation_eligibility", "reading_order", "citation_role", "evidence_status", "context", "search_query", "query_id", "combination", "retention", "citation_weight", "relevance", "journal_authority"))}</tr></thead><tbody>{"".join(index_rows)}</tbody></table>
{_quarantine_html(references_dir)}
<noscript>JavaScript is disabled; the default English view remains available.</noscript></body></html>
"""
        (temporary / "index.html").write_text(index_html, encoding="utf-8")
        output_files.insert(0, "references/literature_summaries/index.html")
        if summary_dir.exists():
            backup = summary_dir.with_name(f"{summary_dir.name}.previous")
            if backup.exists():
                shutil.rmtree(backup)
            summary_dir.replace(backup)
            try:
                temporary.replace(summary_dir)
            except Exception:
                backup.replace(summary_dir)
                raise
            shutil.rmtree(backup)
        else:
            temporary.replace(summary_dir)
        return output_files
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
