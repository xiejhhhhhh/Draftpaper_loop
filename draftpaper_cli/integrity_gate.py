# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .passport import append_integrity_event, read_jsonl
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{([^{}]+)\}",
    re.IGNORECASE,
)
RESULT_CITATION_PATTERN = re.compile(
    r"\\(?:cite|citep|citet|parencite|autocite|textcite)\*?(?:\[[^\]]*\]){0,2}\{",
    re.IGNORECASE,
)

SECTION_FILES = {
    "introduction": ["introduction/introduction.tex", "latex/sections/introduction.tex"],
    "data": ["data/data.tex", "latex/sections/data.tex"],
    "methods": ["methods/methods.tex", "latex/sections/methods.tex"],
    "discussion": ["discussion/discussion.tex", "latex/sections/discussion.tex"],
}

RESULT_FILES = ["results/results.tex", "latex/sections/results.tex"]
BIB_FILES = ["references/library.bib", "latex/library.bib"]
REPORT_JSON = "integrity/integrity_report.json"
REPORT_MD = "integrity/integrity_report.md"


@dataclass
class IntegrityIssue:
    severity: str
    code: str
    message: str
    file: str | None = None
    section: str | None = None


class IntegrityGateError(RuntimeError):
    """Raised when the integrity gate cannot load a DraftPaper project."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bibtex_keys(content: str) -> set[str]:
    return set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", content))


def _citation_keys(content: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION_PATTERN.finditer(content):
        for key in match.group(1).split(","):
            clean = key.strip()
            if clean:
                keys.add(clean)
    return keys


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _project_relative_path(project_path: Path, relative: str, issues: list[IntegrityIssue], *, code: str) -> Path | None:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError:
        issues.append(IntegrityIssue("error", code, f"Path escapes project directory: {relative}", relative))
        return None
    return candidate


def _collect_bib_keys(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    keys: set[str] = set()
    loaded_files: list[str] = []
    for relative in BIB_FILES:
        path = project_path / relative
        if not path.exists():
            continue
        loaded_files.append(relative)
        keys.update(_bibtex_keys(_read_text(path)))
    if not loaded_files:
        issues.append(IntegrityIssue("error", "bib_file_missing", "No BibTeX file found in references/library.bib or latex/library.bib.", "references/library.bib"))
    elif not keys:
        issues.append(IntegrityIssue("error", "bib_no_entries", "BibTeX files contain no entries.", ", ".join(loaded_files)))
    return {"keys": keys, "files": loaded_files}


def _section_citations(project_path: Path) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for section, relatives in SECTION_FILES.items():
        found_files = [relative for relative in relatives if (project_path / relative).exists()]
        text = "\n".join(_read_text(project_path / relative) for relative in found_files)
        report[section] = {
            "files": found_files,
            "citation_keys": sorted(_citation_keys(text)),
        }
    return report


def _check_citations(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    bib = _collect_bib_keys(project_path, issues)
    bib_keys: set[str] = bib["keys"]
    section_report = _section_citations(project_path)
    evidence_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    evidence_by_key: dict[str, list[dict[str, str]]] = {}
    evidence_by_section: dict[str, set[str]] = {}
    for row in evidence_rows:
        key = (row.get("citation_key") or "").strip()
        section = (row.get("section") or "").strip().lower()
        if not key:
            continue
        evidence_by_key.setdefault(key, []).append(row)
        if section:
            evidence_by_section.setdefault(section, set()).add(key)

    missing_bib_keys: set[str] = set()
    missing_evidence: set[str] = set()
    missing_section_evidence: dict[str, list[str]] = {}
    all_section_keys: set[str] = set()
    for section, details in section_report.items():
        cited = set(details["citation_keys"])
        all_section_keys.update(cited)
        missing_bib_keys.update(cited - bib_keys)
        missing_evidence.update(cited - set(evidence_by_key))
        expected = evidence_by_section.get(section, set())
        missing_for_section = sorted(key for key in cited if key not in expected)
        if missing_for_section:
            missing_section_evidence[section] = missing_for_section
            for key in missing_for_section:
                issues.append(IntegrityIssue(
                    "error",
                    "missing_section_citation_evidence",
                    f"Citation {key} is used in {section}, but citation_evidence.csv has no matching section row.",
                    "references/citation_evidence.csv",
                    section,
                ))

    for key in sorted(missing_bib_keys):
        issues.append(IntegrityIssue("error", "missing_bib_key", f"Citation key is absent from BibTeX: {key}", "references/library.bib"))
    for key in sorted(missing_evidence):
        issues.append(IntegrityIssue("error", "missing_citation_evidence", f"Citation key is absent from citation_evidence.csv: {key}", "references/citation_evidence.csv"))

    return {
        "bib_files": bib["files"],
        "bibtex_key_count": len(bib_keys),
        "section_citations": section_report,
        "citation_evidence_row_count": len(evidence_rows),
        "missing_bib_keys": sorted(missing_bib_keys),
        "citations_without_evidence": sorted(missing_evidence),
        "missing_section_evidence": missing_section_evidence,
        "total_section_citation_count": len(all_section_keys),
    }


def _result_entries(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for item in manifest.get("figures") or []:
        if isinstance(item, dict):
            entries.append(("figure", item))
    for item in manifest.get("tables") or []:
        if isinstance(item, dict):
            entries.append(("table", item))
    return entries


def _check_results(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    result_text = "\n".join(_read_text(project_path / relative) for relative in RESULT_FILES if (project_path / relative).exists())
    citation_count = len(RESULT_CITATION_PATTERN.findall(result_text))
    if citation_count:
        issues.append(IntegrityIssue("error", "results_contains_citation", "Results text must not contain literature citation commands.", "results/results.tex", "results"))

    manifest_path = project_path / "results" / "result_manifest.yaml"
    manifest = _read_json(manifest_path)
    entries = _result_entries(manifest)
    if not manifest_path.exists():
        issues.append(IntegrityIssue("error", "result_manifest_missing", "results/result_manifest.yaml is required.", "results/result_manifest.yaml", "results"))
    elif not entries:
        issues.append(IntegrityIssue("error", "result_manifest_empty", "Result manifest must declare at least one figure or table.", "results/result_manifest.yaml", "results"))

    missing_artifacts: list[str] = []
    missing_claims: list[str] = []
    missing_captions: list[str] = []
    for kind, entry in entries:
        entry_id = str(entry.get("id") or entry.get("path") or kind)
        relative = str(entry.get("path") or "").replace("\\", "/")
        if not relative:
            issues.append(IntegrityIssue("error", "result_artifact_path_missing", f"Result entry has no path: {entry_id}", "results/result_manifest.yaml", "results"))
        else:
            path = _project_relative_path(project_path, relative, issues, code="result_artifact_path_escape")
            if path and not path.exists():
                missing_artifacts.append(relative)
                issues.append(IntegrityIssue("error", "result_artifact_missing", f"Result artifact does not exist: {relative}", relative, "results"))
        claim = str(entry.get("result_claim") or "").strip()
        caption = str(entry.get("caption_draft") or "").strip()
        if not claim:
            missing_claims.append(entry_id)
            issues.append(IntegrityIssue("error", "result_claim_missing", f"Result entry lacks a result_claim: {entry_id}", "results/result_manifest.yaml", "results"))
        if not caption:
            missing_captions.append(entry_id)
            issues.append(IntegrityIssue("warning", "result_caption_missing", f"Result entry lacks a caption_draft: {entry_id}", "results/result_manifest.yaml", "results"))
        if RESULT_CITATION_PATTERN.search(claim + "\n" + caption):
            issues.append(IntegrityIssue("error", "result_manifest_contains_citation", f"Result manifest entry contains a citation command: {entry_id}", "results/result_manifest.yaml", "results"))

    return {
        "result_text_files": [relative for relative in RESULT_FILES if (project_path / relative).exists()],
        "citation_command_count": citation_count,
        "manifest": "results/result_manifest.yaml" if manifest_path.exists() else None,
        "artifact_count": len(entries),
        "missing_artifacts": missing_artifacts,
        "missing_claims": missing_claims,
        "missing_captions": missing_captions,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Integrity Gate Report",
        "",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"Errors: {report['error_count']}",
        f"Warnings: {report['warning_count']}",
        "",
        "## Citation Integrity",
        "",
        f"BibTeX keys: {report['citations']['bibtex_key_count']}",
        f"Citation evidence rows: {report['citations']['citation_evidence_row_count']}",
        f"Missing BibTeX keys: {', '.join(report['citations']['missing_bib_keys']) or 'none'}",
        f"Citations without evidence: {', '.join(report['citations']['citations_without_evidence']) or 'none'}",
        "",
        "## Result Integrity",
        "",
        f"Result artifacts declared: {report['results']['artifact_count']}",
        f"Missing result artifacts: {', '.join(report['results']['missing_artifacts']) or 'none'}",
        f"Results citation commands: {report['results']['citation_command_count']}",
        "",
        "## Issues",
        "",
    ]
    if not report["issues"]:
        lines.append("No integrity issues found.")
    else:
        for issue in report["issues"]:
            location = f" ({issue.get('file')})" if issue.get("file") else ""
            lines.append(f"- [{issue['severity']}] {issue['code']}{location}: {issue['message']}")
    return "\n".join(lines) + "\n"


def latest_integrity_report(project: str | Path) -> dict[str, Any] | None:
    project_path = Path(project).expanduser().resolve()
    if project_path.is_file() and project_path.name == "project.json":
        project_path = project_path.parent
    report_path = project_path / REPORT_JSON
    if not report_path.exists():
        return None
    return _read_json(report_path)


def latest_integrity_event(project: str | Path) -> dict[str, Any] | None:
    project_path = Path(project).expanduser().resolve()
    if project_path.is_file() and project_path.name == "project.json":
        project_path = project_path.parent
    events = read_jsonl(project_path / "integrity_ledger.jsonl")
    for event in reversed(events):
        if event.get("kind") == "integrity_gate":
            return event
    return None


def run_integrity_gate(project: str | Path) -> dict[str, Any]:
    """Run citation evidence and result artifact integrity checks."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise IntegrityGateError(str(exc)) from exc

    issues: list[IntegrityIssue] = []
    citations = _check_citations(state.path, issues)
    results = _check_results(state.path, issues)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    status = "passed" if error_count == 0 else "failed"
    report = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": [asdict(issue) for issue in issues],
        "citations": citations,
        "results": results,
    }

    integrity_dir = state.path / "integrity"
    integrity_dir.mkdir(parents=True, exist_ok=True)
    _write_json(integrity_dir / "integrity_report.json", report)
    (integrity_dir / "integrity_report.md").write_text(_render_markdown(report), encoding="utf-8")
    append_integrity_event(state.path, {
        "kind": "integrity_gate",
        "status": status,
        "recorded_at": report["generated_at"],
        "project_id": state.metadata.get("project_id"),
        "error_count": error_count,
        "warning_count": warning_count,
        "report": REPORT_JSON,
    })
    return report
