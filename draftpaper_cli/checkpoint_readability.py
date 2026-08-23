"""Deterministic quality gates for the human-readable checkpoint page."""

from __future__ import annotations

import hashlib
import re
from html import unescape
from typing import Any

from .artifact_identity import canonical_json
from .checkpoint_brief import validate_human_decision_brief


READABILITY_REPORT_SCHEMA = "dpl.checkpoint_readability_report.v1"
MAX_VISIBLE_CHARS = 16000
MAX_TABLES = 12
MAX_LINKS = 64


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _visible_text(html: str) -> str:
    without_script = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", without_script))).strip()


def build_checkpoint_readability_report(
    *,
    html: str,
    brief: dict[str, Any],
    locale: str = "zh-CN",
) -> dict[str, Any]:
    text = _visible_text(html)
    issues = validate_human_decision_brief(brief)
    checks = {
        "utf8_replacement_free": "\ufffd" not in html,
        "charset_declared": "charset=\"utf-8\"" in html.lower() or "charset=utf-8" in html.lower(),
        "viewport_declared": "name=\"viewport\"" in html.lower(),
        "responsive_rules_present": "@media" in html and "max-width" in html,
        "decision_question_present": str((brief.get("decision_question") or {}).get("text_zh") or "") in text,
        "semantic_delta_present": str((brief.get("semantic_delta") or {}).get("summary_zh") or "") in text,
        "reopen_conditions_present": bool(brief.get("reopen_conditions")),
        "brief_contract_valid": not issues,
        "visible_chars_within_budget": len(text) <= MAX_VISIBLE_CHARS,
        "tables_within_budget": len(re.findall(r"<table\b", html, flags=re.IGNORECASE)) <= MAX_TABLES,
        "links_within_budget": len(re.findall(r"<a\b", html, flags=re.IGNORECASE)) <= MAX_LINKS,
        "raw_command_table_absent": "Agent实际工作与本阶段总结" not in text and "原始命令记录" not in text,
    }
    failures = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": READABILITY_REPORT_SCHEMA,
        "locale": locale,
        "visible_character_count": len(text),
        "table_count": len(re.findall(r"<table\b", html, flags=re.IGNORECASE)),
        "link_count": len(re.findall(r"<a\b", html, flags=re.IGNORECASE)),
        "checks": checks,
        "brief_contract_issues": issues,
        "status": "passed" if not failures else "blocked",
        "failure_codes": failures,
    }
    payload["report_sha256"] = _hash(payload)
    return payload


__all__ = ["MAX_LINKS", "MAX_TABLES", "MAX_VISIBLE_CHARS", "READABILITY_REPORT_SCHEMA", "build_checkpoint_readability_report"]
