"""Deterministic quality gates for the human-readable checkpoint page."""

from __future__ import annotations

import hashlib
import re
from html import unescape
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import validate_human_decision_brief


READABILITY_REPORT_SCHEMA = "dpl.checkpoint_readability_report.v1"
MAX_HTML_BYTES = 256 * 1024
MAX_VISIBLE_CHARS = 12000
MAX_TABLES = 8
MAX_TABLE_ROWS = 80
MAX_LINKS = 20
MAX_DECISION_SECTIONS = 16


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _visible_text(html: str) -> str:
    without_script = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", without_script))).strip()


def _statement_rows(brief: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    question = brief.get("decision_question")
    if isinstance(question, dict):
        rows.append(question)
    for field in ("confirming", "key_findings", "claim_boundaries", "not_confirming", "reopen_conditions", "downstream_effects"):
        rows.extend(item for item in brief.get(field) or [] if isinstance(item, dict))
    for item in brief.get("figure_claims") or []:
        if isinstance(item, dict) and isinstance(item.get("statement"), dict):
            rows.append(item["statement"])
    return rows


def _attribute_values(html: str, name: str) -> set[str]:
    pattern = re.compile(rf'\b{re.escape(name)}="([^"]*)"', flags=re.IGNORECASE)
    return {unescape(value).strip() for value in pattern.findall(html) if value.strip()}


def _display_text(statement: dict[str, Any], locale: str) -> str:
    if locale == "en" and str(statement.get("text_en") or "").strip():
        return str(statement.get("text_en") or "").strip()
    return str(statement.get("text_zh") or "").strip()


def _safe_artifact_refs(brief: dict[str, Any]) -> bool:
    for fact in brief.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        for ref in fact.get("evidence_refs") or []:
            text = str(ref or "")
            if not text.startswith("artifact:"):
                continue
            relative = text[len("artifact:") :].replace("\\", "/")
            path = Path(relative)
            if not relative or path.is_absolute() or ".." in path.parts:
                return False
    return True


def _priority_order_ok(html: str, locale: str) -> bool:
    labels = (
        (
            "What this decision confirms",
            "Key facts for this decision",
            "Claim boundaries",
            "What this decision does not confirm",
            "When scientific confirmation is required again",
        )
        if locale == "en"
        else ("本次确认什么", "本次决定的关键事实", "论断边界", "本次不确认什么", "何时会重新要求科学确认")
    )
    headings = [unescape(re.sub(r"<[^>]+>", "", value)).strip() for value in re.findall(r"<h2\b[^>]*>(.*?)</h2>", html, flags=re.IGNORECASE | re.DOTALL)]
    positions = [headings.index(label) if label in headings else -1 for label in labels]
    return all(position >= 0 for position in positions) and positions == sorted(positions)


def _mobile_layout_contract(html: str) -> bool:
    lowered = html.lower()
    required = (
        "@media (max-width:680px)",
        "grid-template-columns:minmax(0,1fr)",
        "overflow-wrap:anywhere",
        "min-width:0",
        "max-width:980px",
    )
    return all(token in lowered for token in required)


def _expected_fact_ids(brief: dict[str, Any]) -> set[str]:
    return {
        str(item.get("fact_id") or "").strip()
        for item in brief.get("facts") or []
        if isinstance(item, dict) and str(item.get("fact_id") or "").strip()
    }


def _expected_statement_ids(brief: dict[str, Any]) -> set[str]:
    return {
        str(item.get("statement_id") or "").strip()
        for item in _statement_rows(brief)
        if str(item.get("statement_id") or "").strip()
    }


def build_checkpoint_readability_report(
    *,
    html: str,
    brief: dict[str, Any],
    locale: str = "zh-CN",
) -> dict[str, Any]:
    """Verify a compact, complete author-decision surface.

    This is a deterministic structural gate. It verifies the source Brief,
    rendered statement/fact IDs, reference safety, and the responsive CSS
    contract without treating a browser screenshot as scientific evidence.
    """

    normalized_locale = "en" if locale == "en" else "zh-CN"
    text = _visible_text(html)
    issues = validate_human_decision_brief(brief)
    expected_statement_ids = _expected_statement_ids(brief)
    rendered_statement_ids = _attribute_values(html, "data-statement-id")
    rendered_fact_ids = _attribute_values(html, "data-fact-id")
    for values in _attribute_values(html, "data-fact-refs"):
        rendered_fact_ids.update(value for value in values.split() if value)
    expected_fact_ids = _expected_fact_ids(brief)
    question = brief.get("decision_question") if isinstance(brief.get("decision_question"), dict) else {}
    delta = brief.get("semantic_delta") if isinstance(brief.get("semantic_delta"), dict) else {}
    expected_delta = str(delta.get("summary_en") or "") if normalized_locale == "en" else str(delta.get("summary_zh") or "")
    if not expected_delta:
        expected_delta = str(delta.get("summary_zh") or "")
    html_bytes = len(html.encode("utf-8"))
    table_count = len(re.findall(r"<table\b", html, flags=re.IGNORECASE))
    table_row_count = len(re.findall(r"<tr\b", html, flags=re.IGNORECASE))
    link_count = len(re.findall(r"<a\b", html, flags=re.IGNORECASE))
    decision_section_count = len(re.findall(r"<h2\b", html, flags=re.IGNORECASE))
    checks = {
        "utf8_replacement_free": "\ufffd" not in html,
        "charset_declared": "charset=\"utf-8\"" in html.lower() or "charset=utf-8" in html.lower(),
        "viewport_declared": "name=\"viewport\"" in html.lower(),
        "locale_declared": f'<html lang="{normalized_locale.lower()}"' in html.lower(),
        "responsive_layout_contract": _mobile_layout_contract(html),
        "decision_state_present": '<span class="status">' in html,
        "priority_sections_in_order": _priority_order_ok(html, normalized_locale),
        "decision_question_present": _display_text(question, normalized_locale) in text,
        "semantic_delta_present": expected_delta in text,
        "reopen_conditions_present": bool(brief.get("reopen_conditions")),
        "brief_contract_valid": not issues,
        "rendered_statement_coverage": expected_statement_ids <= rendered_statement_ids,
        "rendered_fact_coverage": expected_fact_ids <= rendered_fact_ids,
        "artifact_refs_project_safe": _safe_artifact_refs(brief),
        "html_bytes_within_budget": html_bytes <= MAX_HTML_BYTES,
        "visible_chars_within_budget": len(text) <= MAX_VISIBLE_CHARS,
        "decision_sections_within_budget": decision_section_count <= MAX_DECISION_SECTIONS,
        "tables_within_budget": table_count <= MAX_TABLES,
        "table_rows_within_budget": table_row_count <= MAX_TABLE_ROWS,
        "links_within_budget": link_count <= MAX_LINKS,
        "raw_command_table_absent": "Agent实际工作与本阶段总结" not in text and "原始命令记录" not in text,
    }
    failures = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": READABILITY_REPORT_SCHEMA,
        "locale": normalized_locale,
        "html_byte_count": html_bytes,
        "visible_character_count": len(text),
        "decision_section_count": decision_section_count,
        "table_count": table_count,
        "table_row_count": table_row_count,
        "link_count": link_count,
        "expected_statement_ids": sorted(expected_statement_ids),
        "rendered_statement_ids": sorted(rendered_statement_ids),
        "expected_fact_ids": sorted(expected_fact_ids),
        "rendered_fact_ids": sorted(rendered_fact_ids),
        "checks": checks,
        "brief_contract_issues": issues,
        "status": "passed" if not failures else "blocked",
        "failure_codes": failures,
    }
    payload["report_sha256"] = _hash(payload)
    return payload


__all__ = [
    "MAX_DECISION_SECTIONS",
    "MAX_HTML_BYTES",
    "MAX_LINKS",
    "MAX_TABLE_ROWS",
    "MAX_TABLES",
    "MAX_VISIBLE_CHARS",
    "READABILITY_REPORT_SCHEMA",
    "build_checkpoint_readability_report",
]
