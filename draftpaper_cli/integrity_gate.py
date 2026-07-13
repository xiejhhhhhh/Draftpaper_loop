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

MANUSCRIPT_LANGUAGE_FILES = {
    "introduction": ["introduction/introduction.tex", "latex/sections/introduction.tex"],
    "data": ["data/data.tex", "latex/sections/data.tex"],
    "methods": ["methods/methods.tex", "latex/sections/methods.tex"],
    "results": ["results/results.tex", "latex/sections/results.tex"],
    "discussion": ["discussion/discussion.tex", "latex/sections/discussion.tex"],
    "main": ["latex/main.tex"],
}

FORBIDDEN_MANUSCRIPT_PATTERNS = [
    ("local_project_artifact", re.compile(r"\blocal project artifact\b", re.IGNORECASE)),
    ("draftpaper_project_language", re.compile(r"\bDraftPaper project\b|\bdraftpaper-loop workflow\b", re.IGNORECASE)),
    ("workflow_report_leak", re.compile(r"\bworkflow\.html\b|\bstage-owned\b|\bformula extraction layer\b|\bfigure-code trace\b|\bmanifest internals\b", re.IGNORECASE)),
    ("file_path_language", re.compile(r"\b(?:filename|pathname|storage path|local path)\b", re.IGNORECASE)),
    ("execution_smoke_language", re.compile(r"\b(?:training_)?smoke[_-]?test\b|\b(?:XRB|TDE|AGN)[_-]?verify\b", re.IGNORECASE)),
    ("generator_instruction_language", re.compile(r"\bcurrent draft should\b|\bmanuscript should\b", re.IGNORECASE)),
    ("placeholder_author", re.compile(
        r"\bDraft Author\b|\bDraft affiliation\b|\bManuscript author to be supplied\b|"
        r"\bAffiliation to be supplied\b|placeholder(?:\.invalid)?|"
        r"\b(?:abstract\s+is\s+a\s+placeholder|placeholder abstract)\b",
        re.IGNORECASE,
    )),
]


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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _sample_composition_totals(project_path: Path) -> dict[str, int]:
    rows = _read_csv_rows(project_path / "results" / "tables" / "sample_composition.csv")
    totals = {"event_count": 0, "source_count": 0}
    for row in rows:
        for key in totals:
            value = _as_float(row.get(key))
            if value is not None:
                totals[key] += int(round(value))
    return {key: value for key, value in totals.items() if value > 0}


def _run_aware_sample_totals(project_path: Path) -> dict[str, Any]:
    snapshot = _read_json(project_path / "results" / "promoted_evidence_snapshot.json")
    registry = _read_json(project_path / "writing" / "scientific_evidence_registry.json")
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json")
    if not snapshot or not registry:
        return {"status": "unavailable", "totals": {}, "records": [], "conflicts": []}
    active_run = str(resolved.get("run_id") or "")
    promoted_artifacts = set((snapshot.get("artifacts") or {}).keys())
    selected: dict[str, list[dict[str, Any]]] = {"event_count": [], "source_count": []}
    for record in registry.get("records") or []:
        if not isinstance(record, dict):
            continue
        role = str(record.get("entity_role") or "")
        if role not in selected or not record.get("binding_complete", True):
            continue
        run_id = str(record.get("run_id") or "")
        cohort = str(record.get("cohort_id") or record.get("cohort") or "main").lower()
        source = str(record.get("source_artifact") or "")
        if active_run and run_id not in {active_run, "not_applicable"}:
            continue
        if cohort not in {"main", "primary", "main_modeling_sample"}:
            continue
        if source and source not in promoted_artifacts:
            continue
        numeric = _as_float(record.get("value"))
        if numeric is not None and numeric > 0:
            selected[role].append(record)
    totals: dict[str, int] = {}
    conflicts = []
    for role, records in selected.items():
        values = {int(round(float(item["value"]))) for item in records}
        if len(values) == 1:
            totals[role] = next(iter(values))
        elif len(values) > 1:
            conflicts.append({"entity_role": role, "values": sorted(values), "evidence_ids": [item.get("evidence_id") for item in records]})
    return {
        "status": "conflict" if conflicts else "resolved" if totals else "unavailable",
        "active_run_id": active_run or None,
        "snapshot_id": snapshot.get("snapshot_id"),
        "totals": totals,
        "records": [item for records in selected.values() for item in records],
        "conflicts": conflicts,
    }


def _sentences(text: str) -> list[str]:
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+|\n+", text) if piece.strip()]


def _count_role(sentence: str, unit: str, start: int = 0, end: int | None = None) -> str:
    lowered_sentence = sentence.lower()
    end = len(sentence) if end is None else end
    lowered = sentence[max(0, start - 80): min(len(sentence), end + 80)].lower()
    if re.search(r"\b(?:row|rows|table rows|records after join|joined records)\b", lowered):
        return "row_count"
    if re.search(r"\b(?:parser|parsed|parse|smoke|sanity|diagnostic|manual check|quality check|subset)\b", lowered):
        return "parser_validation_subset"
    if re.search(r"\b(?:train|training|validation|test|held-out|holdout|split|fold|cross-validation)\b", lowered):
        return "model_validation_subset"
    if re.search(r"\b(?:history|source-history|token|tokens|sequence|sequences)\b", lowered):
        return "history_token_count"
    if re.search(r"\b(?:agn|xrb|tde|qpe|ulx|class-specific|per-class|category)\b", lowered):
        return "class_specific_count"
    if re.search(r"\b(?:coverage|matched|counterpart|cross-match|crossmatched)\b", lowered):
        return "coverage_count"
    if unit == "event_count" and re.search(
        r"\b(?:study uses|study includes|dataset contains|data set contains|evidence base contains|sample comprises|sample contains|analysis uses|research sample contains|cohort contains|consists of)\b",
        lowered_sentence,
    ):
        return "main_modeling_sample"
    if unit == "source_count" and re.search(
        r"\b(?:study uses|study includes|dataset contains|data set contains|evidence base contains|sample comprises|sample contains|analysis uses|research sample contains|cohort contains|from)\b",
        lowered_sentence,
    ):
        return "main_modeling_sample"
    return "context_specific_count"


def _extract_declared_counts(text: str, unit: str) -> list[dict[str, Any]]:
    if unit == "event_count":
        patterns = [
            r"\b(\d{2,8})\s+(?:parsed\s+|labelled\s+|labeled\s+)?(?:event|events|observations|records)\b",
            r"\b(?:event|events|observations|records)\s*(?:=|:|total(?:ed)?\s*)\s*(\d{2,8})\b",
        ]
    else:
        patterns = [
            r"\b(\d{1,8})\s+source-history\s+tokens\b",
            r"\b(\d{1,8})\s+(?:unique\s+)?(?:source|sources|objects)(?!-)\b",
            r"\b(?:source|sources|objects)(?!-)\s*(?:=|:|total(?:ed)?\s*)\s*(\d{1,8})\b",
        ]
    counts: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for sentence in _sentences(text):
        for pattern in patterns:
            for match in re.finditer(pattern, sentence, flags=re.IGNORECASE):
                try:
                    value = int(match.group(1))
                except Exception:
                    continue
                matched_text = match.group(0).lower()
                role = "history_token_count" if "source-history" in matched_text else _count_role(sentence, unit, match.start(), match.end())
                key = (value, role, sentence)
                if key in seen:
                    continue
                seen.add(key)
                counts.append({"value": value, "role": role, "sentence": sentence})
    return counts


def _check_manuscript_language(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for section, relatives in MANUSCRIPT_LANGUAGE_FILES.items():
        for relative in relatives:
            path = project_path / relative
            if not path.exists():
                continue
            text = _read_text(path)
            for code, pattern in FORBIDDEN_MANUSCRIPT_PATTERNS:
                if pattern.search(text):
                    findings.append({"section": section, "file": relative, "code": code})
                    issues.append(IntegrityIssue(
                        "error",
                        "manuscript_internal_language",
                        f"Manuscript text contains internal or storage-oriented language ({code}); rewrite as scientific prose before final quality check.",
                        relative,
                        section,
                    ))
    return {"finding_count": len(findings), "findings": findings}


def _check_writing_brief_coverage(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    data_brief = _read_json(project_path / "data" / "data_writing_brief.json")
    data_text = _read_text(project_path / "data" / "data.tex") if (project_path / "data" / "data.tex").exists() else ""
    if data_brief and data_text:
        lowered = data_text.lower()
        role_terms = {
            "data_source": ["source", "survey", "database", "record", "observation"],
            "processed_dataset": ["processed", "analysis-ready", "dataset", "data set", "sample"],
            "feature_content_groups": ["variable", "feature", "covariate", "index", "token", "spectral"],
            "missingness_coverage": ["missing", "coverage", "quality", "available", "complete"],
            "claim_boundary": ["bounded", "boundary", "limited", "support", "claim"],
        }
        missing_roles = []
        for role in data_brief.get("required_coverage") or []:
            terms = role_terms.get(str(role), [])
            if terms and not any(term in lowered for term in terms):
                missing_roles.append(role)
        if missing_roles:
            findings.append({"section": "data", "missing_roles": missing_roles})
            issues.append(IntegrityIssue(
                "warning",
                "data_writing_brief_coverage_gap",
                "Data text may not cover all required writing-brief roles: " + ", ".join(str(item) for item in missing_roles),
                "data/data.tex",
                "data",
            ))
    method_brief = _read_json(project_path / "methods" / "method_writing_brief.json")
    method_text = _read_text(project_path / "methods" / "methods.tex") if (project_path / "methods" / "methods.tex").exists() else ""
    formula_manifest = _read_json(project_path / "methods" / "method_formula_manifest.json")
    formula_count = int(formula_manifest.get("formula_count") or len(formula_manifest.get("formulas") or [])) if formula_manifest else 0
    method_findings: dict[str, Any] = {}
    if method_brief and method_text:
        lowered = method_text.lower()
        stage_terms = {
            "sample_construction": ["sample", "cohort", "observation", "event"],
            "feature_or_token_construction": ["feature", "token", "representation", "variable"],
            "model_architecture": ["model", "classifier", "regression", "architecture", "estimator"],
            "training_objective": ["loss", "objective", "optimization", "fit", "training"],
            "validation_design": ["validation", "held-out", "cross-validation", "split", "blocked"],
            "metrics_and_ablation": ["metric", "auc", "accuracy", "f1", "r2", "ablation", "baseline"],
        }
        missing_stages = []
        for stage in method_brief.get("required_coverage") or []:
            terms = stage_terms.get(str(stage), [])
            if terms and not any(term in lowered for term in terms):
                missing_stages.append(stage)
        if missing_stages:
            method_findings["missing_stages"] = missing_stages
            issues.append(IntegrityIssue(
                "warning",
                "method_writing_brief_coverage_gap",
                "Methods text may not cover all required writing-brief stages: " + ", ".join(str(item) for item in missing_stages),
                "methods/methods.tex",
                "methods",
            ))
    if formula_count and method_text:
        if "\\begin{equation}" not in method_text:
            method_findings["missing_equation_blocks"] = True
            issues.append(IntegrityIssue(
                "error",
                "method_formula_not_rendered",
                "A method formula manifest exists, but methods.tex does not contain displayed equation blocks.",
                "methods/methods.tex",
                "methods",
            ))
        if not re.search(r"\b(?:denotes|represents|is the|are the|variables? include)\b", method_text, flags=re.IGNORECASE):
            method_findings["missing_variable_explanation"] = True
            issues.append(IntegrityIssue(
                "error",
                "method_formula_variables_not_explained",
                "Formula-bearing Methods text must explain the variables near the displayed equations.",
                "methods/methods.tex",
                "methods",
            ))
    if method_findings:
        findings.append({"section": "methods", **method_findings})
    return {"finding_count": len(findings), "findings": findings}


def _check_evidence_number_consistency(project_path: Path, issues: list[IntegrityIssue]) -> dict[str, Any]:
    run_aware = _run_aware_sample_totals(project_path)
    if run_aware.get("conflicts"):
        issues.append(IntegrityIssue(
            "error",
            "run_aware_cohort_conflict",
            "The promoted evidence registry contains conflicting top-level cohort counts for the same active run.",
            "writing/scientific_evidence_registry.json",
        ))
        return {"sample_composition": None, "source": "promoted_evidence_registry", "checked": False, "mismatches": [], "observed_counts": [], "run_aware": run_aware}
    totals = dict(run_aware.get("totals") or {})
    source = "promoted_evidence_registry"
    if not totals:
        totals = _sample_composition_totals(project_path)
        source = "legacy_sample_composition_compatibility"
    if not totals:
        return {"sample_composition": None, "source": source, "checked": False, "mismatches": [], "observed_counts": [], "run_aware": run_aware}
    data_text = "\n".join(_read_text(project_path / relative) for relative in ["data/data.tex", "latex/sections/data.tex"] if (project_path / relative).exists())
    result_text = "\n".join(_read_text(project_path / relative) for relative in RESULT_FILES if (project_path / relative).exists())
    combined = {"data": data_text, "results": result_text}
    mismatches: list[dict[str, Any]] = []
    observed_counts: list[dict[str, Any]] = []
    for unit, expected in totals.items():
        for section, text in combined.items():
            if not text:
                continue
            declared = _extract_declared_counts(text, unit)
            for count in declared:
                value = int(count["value"])
                role = str(count["role"])
                observed_counts.append({
                    "section": section,
                    "unit": unit,
                    "value": value,
                    "role": role,
                    "checked_against_sample_composition": role == "main_modeling_sample",
                })
                if role != "main_modeling_sample":
                    continue
                if value != expected:
                    label = "events" if unit == "event_count" else "sources"
                    mismatch = {"section": section, "unit": unit, "role": role, "declared": value, "expected": expected}
                    mismatches.append(mismatch)
                    issues.append(IntegrityIssue(
                        "error",
                        "evidence_number_mismatch",
                        f"{section.title()} declares {value} {label}, but the active {source} evidence records {expected}.",
                        f"{section}/{section}.tex" if section != "results" else "results/results.tex",
                        section,
                    ))
    return {"sample_composition": totals, "source": source, "checked": True, "mismatches": mismatches, "observed_counts": observed_counts, "run_aware": run_aware}


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
        "## Manuscript Language",
        "",
        f"Internal-language findings: {report['manuscript_language']['finding_count']}",
        f"Writing-brief findings: {report.get('writing_briefs', {}).get('finding_count', 0)}",
        "",
        "## Evidence Number Consistency",
        "",
        f"Checked sample composition: {report['evidence_numbers']['checked']}",
        f"Mismatches: {len(report['evidence_numbers']['mismatches'])}",
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
    manuscript_language = _check_manuscript_language(state.path, issues)
    writing_briefs = _check_writing_brief_coverage(state.path, issues)
    evidence_numbers = _check_evidence_number_consistency(state.path, issues)
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
        "manuscript_language": manuscript_language,
        "writing_briefs": writing_briefs,
        "evidence_numbers": evidence_numbers,
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
