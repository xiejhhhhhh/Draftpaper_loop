# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any

from .metadata import GENERATOR_HTML_META
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}",
    re.IGNORECASE,
)
BIB_ENTRY_PATTERN = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@\w+\s*\{|$)", re.IGNORECASE | re.DOTALL)
BIB_FIELD_PATTERN = re.compile(r"(\w+)\s*=\s*[\{\"]([^}\"]*)[\}\"]", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

SECTION_FILES = {
    "introduction": ["introduction/introduction.tex", "latex/sections/introduction.tex"],
    "data": ["data/data.tex", "latex/sections/data.tex"],
    "methods": ["methods/methods.tex", "latex/sections/methods.tex"],
    "discussion": ["discussion/discussion.tex", "latex/sections/discussion.tex"],
}

STOPWORDS = {
    "about",
    "after",
    "also",
    "among",
    "based",
    "because",
    "been",
    "being",
    "between",
    "both",
    "could",
    "data",
    "does",
    "from",
    "have",
    "into",
    "model",
    "models",
    "more",
    "paper",
    "results",
    "show",
    "study",
    "such",
    "that",
    "their",
    "these",
    "this",
    "using",
    "were",
    "when",
    "with",
}


@dataclass
class CitationUsage:
    usage_id: str
    citation_key: str
    section: str
    file: str
    passage: str
    claim: str
    verdict: str
    match_score: float
    reasoning: str
    supporting_evidence: str
    doi: str
    url: str
    needs_review: bool


class CitationAuditError(RuntimeError):
    """Raised when the citation audit loop cannot load project artifacts."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _read_bib(project_path: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    content = "\n".join(
        _read_text(project_path / relative)
        for relative in ["references/library.bib", "latex/library.bib"]
        if (project_path / relative).exists()
    )
    for match in BIB_ENTRY_PATTERN.finditer(content):
        key = match.group(1).strip()
        body = match.group(2)
        fields = {field.group(1).lower(): field.group(2).strip() for field in BIB_FIELD_PATTERN.finditer(body)}
        entries[key] = fields
    return entries


def _read_evidence(project_path: Path) -> dict[str, list[dict[str, str]]]:
    path = project_path / "references" / "citation_evidence.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("citation_key") or "").strip()
        if key:
            evidence.setdefault(key, []).append(row)
    return evidence


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in WORD_PATTERN.findall(text) if token.lower() not in STOPWORDS}


def _clean_latex(text: str) -> str:
    text = CITATION_PATTERN.sub("", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r"\1", text)
    text = text.replace("~", " ")
    return re.sub(r"\s+", " ", text).strip()


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?。！？])\s+", text):
        end = match.start()
        sentence = text[start:end].strip()
        if sentence:
            spans.append((start, end, sentence))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        spans.append((start, len(text), tail))
    return spans


def _best_passage_for_citation(text: str, match_start: int) -> str:
    for start, end, sentence in _sentence_spans(text):
        if start <= match_start <= end:
            return sentence
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ""


def _judge_usage(key: str, section: str, passage: str, bib: dict[str, dict[str, str]], evidence: dict[str, list[dict[str, str]]]) -> tuple[str, float, str, str, str, str]:
    if key not in bib:
        return "unverifiable", 0.0, "The citation key is absent from BibTeX, so the cited source cannot be resolved.", "", "", ""
    rows = evidence.get(key) or []
    if not rows:
        fields = bib.get(key) or {}
        return "unverifiable", 0.0, "The source exists in BibTeX but has no citation_evidence row for claim-level checking.", "", fields.get("doi", ""), fields.get("url", "")
    section_rows = [row for row in rows if (row.get("section") or "").strip().lower() == section]
    candidate_rows = section_rows or rows
    claim_tokens = _tokens(_clean_latex(passage))
    best_row: dict[str, str] = candidate_rows[0]
    best_score = 0.0
    for row in candidate_rows:
        evidence_text = " ".join(str(row.get(name) or "") for name in ["claim", "evidence_summary", "source", "doi", "url"])
        evidence_tokens = _tokens(evidence_text)
        if not claim_tokens or not evidence_tokens:
            score = 0.0
        else:
            score = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
        if score >= best_score:
            best_score = score
            best_row = row
    supporting = str(best_row.get("evidence_summary") or best_row.get("claim") or "")
    doi = str(best_row.get("doi") or (bib.get(key) or {}).get("doi") or "")
    url = str(best_row.get("url") or (bib.get(key) or {}).get("url") or "")
    if best_score >= 0.28:
        return "supported", round(best_score, 3), "The cited evidence overlaps with the local claim at a source-specific level.", supporting, doi, url
    if best_score >= 0.18:
        return "partially_supported", round(best_score, 3), "The citation is topically related, but the local claim should be narrowed or supplemented.", supporting, doi, url
    return "unsupported", round(best_score, 3), "The local claim does not align with the stored evidence for this citation.", supporting, doi, url


def _collect_usages(project_path: Path, bib: dict[str, dict[str, str]], evidence: dict[str, list[dict[str, str]]]) -> list[CitationUsage]:
    usages: list[CitationUsage] = []
    seen: set[tuple[str, str, str]] = set()
    for section, relatives in SECTION_FILES.items():
        for relative in relatives:
            path = project_path / relative
            if not path.exists():
                continue
            text = _read_text(path)
            for match in CITATION_PATTERN.finditer(text):
                passage = _best_passage_for_citation(text, match.start())
                for raw_key in match.group(1).split(","):
                    key = raw_key.strip()
                    if not key:
                        continue
                    dedupe = (relative, key, passage)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    verdict, score, reasoning, supporting, doi, url = _judge_usage(key, section, passage, bib, evidence)
                    usage_id = f"{section}_{len(usages) + 1:03d}_{re.sub(r'[^A-Za-z0-9_-]+', '_', key)}"
                    usages.append(CitationUsage(
                        usage_id=usage_id,
                        citation_key=key,
                        section=section,
                        file=relative,
                        passage=passage,
                        claim=_clean_latex(passage),
                        verdict=verdict,
                        match_score=score,
                        reasoning=reasoning,
                        supporting_evidence=supporting,
                        doi=doi,
                        url=url,
                        needs_review=verdict in {"unsupported", "unverifiable"} or (verdict == "partially_supported" and score < 0.55),
                    ))
    return usages


def _summary(usages: list[CitationUsage]) -> dict[str, Any]:
    counts = {name: 0 for name in ["supported", "partially_supported", "unsupported", "unverifiable"]}
    for usage in usages:
        counts[usage.verdict] = counts.get(usage.verdict, 0) + 1
    blocking = counts["unsupported"] + counts["unverifiable"]
    low_confidence = sum(1 for usage in usages if usage.match_score < 0.55)
    average = round(sum(usage.match_score for usage in usages) / len(usages), 3) if usages else 1.0
    return {
        "total_usages": len(usages),
        "supported": counts["supported"],
        "partially_supported": counts["partially_supported"],
        "unsupported": counts["unsupported"],
        "unverifiable": counts["unverifiable"],
        "low_confidence": low_confidence,
        "blocking_issue_count": blocking,
        "average_match_score": average,
    }


def _next_iteration(audit_dir: Path) -> int:
    iteration_dir = audit_dir / "iterations"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    indices = []
    for path in iteration_dir.glob("citation_audit_iteration_*.html"):
        match = re.search(r"_(\d+)\.html$", path.name)
        if match:
            indices.append(int(match.group(1)))
    return (max(indices) + 1) if indices else 1


def _render_html(report: dict[str, Any], *, title: str) -> str:
    summary = report.get("summary") or {}
    rows = []
    for usage in report.get("usages") or []:
        verdict = str(usage.get("verdict") or "unverifiable")
        score = float(usage.get("match_score") or 0)
        percent = max(0, min(100, int(round(score * 100))))
        rows.append(
            "<article class='ref-card'>"
            f"<div class='card-head'><span class='ref-id'>{escape(str(usage.get('citation_key') or ''))}</span>"
            f"<span class='verdict verdict-{escape(verdict)}'>{escape(verdict)}</span></div>"
            f"<p class='meta'>{escape(str(usage.get('section') or ''))} · {escape(str(usage.get('file') or ''))}</p>"
            f"<p><strong>Claim</strong>: {escape(str(usage.get('claim') or ''))}</p>"
            f"<p><strong>Evidence</strong>: {escape(str(usage.get('supporting_evidence') or ''))}</p>"
            f"<p><strong>Reasoning</strong>: {escape(str(usage.get('reasoning') or ''))}</p>"
            f"<div class='score'><span style='width:{percent}%'></span></div><p class='meta'>match score {score:.3f}</p>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
{GENERATOR_HTML_META.rstrip()}
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg-paper:#faf9f5; --bg-soft:#f5f3ec; --ink:#1a1d2a; --ink-soft:#4a4f5f;
      --hairline:#e7e4d9; --positive:#0891b2; --attention:#8a6d3b; --negative:#c0392b; --neutral:#4a4f5f;
      --positive-bg:#e6f9fc; --attention-bg:#faf3e4; --negative-bg:#fbeceb; --neutral-bg:#f1f0ec;
    }}
    body {{ font-family: Georgia, 'Noto Serif SC', serif; color:var(--ink); background:var(--bg-paper); max-width:1000px; margin:0 auto; padding:40px 32px 80px; line-height:1.7; }}
    .report-header {{ display:flex; gap:18px; align-items:center; border-bottom:1px solid var(--hairline); padding-bottom:18px; margin-bottom:28px; }}
    .seal {{ width:56px; height:56px; border-radius:12px; background:var(--negative); color:white; display:flex; align-items:center; justify-content:center; font-size:28px; font-weight:700; }}
    h1 {{ font-size:28px; margin:0; }} .subtitle,.meta {{ color:var(--ink-soft); font-size:13px; }}
    .summary-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:22px 0 30px; }}
    .summary-card {{ background:var(--bg-soft); border:1px solid var(--hairline); border-radius:8px; padding:14px; text-align:center; }}
    .summary-card .num {{ font-family:Consolas,monospace; font-size:26px; }}
    .ref-card {{ background:white; border:1px solid var(--hairline); border-radius:8px; padding:18px; margin:14px 0; }}
    .card-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
    .ref-id {{ font-family:Consolas,monospace; font-weight:700; }}
    .verdict {{ border-radius:999px; padding:3px 10px; font-family:Consolas,monospace; font-size:12px; }}
    .verdict-supported {{ color:var(--positive); background:var(--positive-bg); }}
    .verdict-partially_supported {{ color:var(--attention); background:var(--attention-bg); }}
    .verdict-unsupported {{ color:var(--negative); background:var(--negative-bg); }}
    .verdict-unverifiable {{ color:var(--neutral); background:var(--neutral-bg); }}
    .score {{ height:7px; background:#e7e4d9; border-radius:999px; overflow:hidden; }}
    .score span {{ display:block; height:100%; background:var(--positive); }}
  </style>
</head>
<body>
  <header class="report-header"><div class="seal">引</div><div><h1>{escape(title)}</h1><p class="subtitle">Generated at {escape(str(report.get('generated_at') or ''))} · status {escape(str(report.get('status') or ''))}</p></div></header>
  <section class="summary-grid">
    <div class="summary-card"><div class="num">{summary.get('total_usages', 0)}</div><div>citation usages</div></div>
    <div class="summary-card"><div class="num">{summary.get('supported', 0)}</div><div>supported</div></div>
    <div class="summary-card"><div class="num">{summary.get('partially_supported', 0)}</div><div>partial</div></div>
    <div class="summary-card"><div class="num">{summary.get('unsupported', 0)}</div><div>unsupported</div></div>
    <div class="summary-card"><div class="num">{summary.get('unverifiable', 0)}</div><div>unverifiable</div></div>
  </section>
  <h2>Claim-level Citation Audit</h2>
  {''.join(rows) if rows else '<p>No citation usages were found.</p>'}
</body>
</html>
"""


def audit_citations(project: str | Path, *, final: bool = False) -> dict[str, Any]:
    """Run a local claim-level citation audit and write JSON/HTML reports."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise CitationAuditError(str(exc)) from exc

    bib = _read_bib(state.path)
    evidence = _read_evidence(state.path)
    usages = _collect_usages(state.path, bib, evidence)
    summary = _summary(usages)
    status = "passed" if summary["blocking_issue_count"] == 0 else "failed"
    report = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "strict_target": {
            "unsupported": 0,
            "unverifiable": 0,
            "not_found": 0,
            "missing_from_list": 0,
            "orphan_in_list": 0,
            "minimum_average_match_score": 0.65,
        },
        "summary": summary,
        "usages": [asdict(usage) for usage in usages],
    }
    audit_dir = state.path / "citation_audit"
    iteration_dir = audit_dir / "iterations"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "citation_audit_report.json", report)
    title = "引用核查报告" if not final else "最终达标引用核查报告"
    html = _render_html(report, title=title)
    (audit_dir / "citation_audit_report.html").write_text(html, encoding="utf-8")
    index = _next_iteration(audit_dir)
    (iteration_dir / f"citation_audit_iteration_{index:03d}.html").write_text(html, encoding="utf-8")
    if final and status == "passed":
        (audit_dir / "final_citation_audit_report.html").write_text(html, encoding="utf-8")
        _write_json(audit_dir / "final_citation_audit_report.json", report)
    return report
