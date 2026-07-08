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

from .citation_utils import bibtex_keys_in_text, citation_keys_in_text, has_citation_command
from .io_utils import read_json, read_text
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status, validate_project
from .writing_quality import evaluate_section_quality


QUALITY_INPUTS = [
    "project.json",
    "latex/main.tex",
    "latex/library.bib",
    "latex/sections/introduction.tex",
    "latex/sections/data.tex",
    "latex/sections/methods.tex",
    "latex/sections/results.tex",
    "latex/sections/discussion.tex",
    "journal_profile/journal_profile.json",
    "journal_profile/journal_guidelines.md",
    "data/data_inventory.json",
    "data/data_quality_report.json",
    "data/data_feasibility_report.json",
    "data/data_writing_context.json",
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "methods/run_manifest.yaml",
    "methods/method_writing_context.json",
    "results/result_validity_report.json",
    "core_evidence/core_evidence_report.json",
    "results/result_manifest.yaml",
    "results/results.tex",
    "results/results_summary_zh.md",
    "references/citation_evidence.csv",
    "citation_audit/final_citation_audit_report.json",
]

QUALITY_OUTPUTS = [
    "quality_checks/quality_report.json",
]

FINAL_INPUT_STAGES = [
    "references",
    "journal_profile",
    "research_plan",
    "data",
    "method_plan",
    "figure_plan",
    "code",
    "methods",
    "result_validity",
    "core_evidence",
    "results",
    "introduction",
    "data_writing",
    "methods_writing",
    "discussion",
    "latex",
]
FILESYSTEM_PATTERN = re.compile(
    r"([A-Za-z]:\\|(?:data|results|code)/(?:raw|processed|figures|tables|scripts)/|\b[\w.-]+\.(?:csv|tsv|xlsx|xls|json|py|svg|png|jpg|jpeg)\b)",
    re.IGNORECASE,
)
METHOD_EXECUTION_PATTERN = re.compile(r"(\\texttt\{|recorded command|output files?|run_manifest|code/scripts|python\s+code/)", re.IGNORECASE)


@dataclass
class QualityIssue:
    severity: str
    code: str
    message: str
    file: str | None = None


class QualityGateError(RuntimeError):
    """Raised when the quality gate cannot run because the project cannot be loaded."""


def _read_text(path: Path) -> str:
    return read_text(path)


def _read_json(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _bibtex_keys(content: str) -> set[str]:
    return bibtex_keys_in_text(content)


def _latex_citation_keys(content: str) -> set[str]:
    return citation_keys_in_text(content)


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _project_relative_path(project_path: Path, relative: str, issues: list[QualityIssue], *, code: str) -> Path | None:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError:
        issues.append(QualityIssue("error", code, f"Path escapes project directory: {relative}", relative))
        return None
    return candidate


def _check_required_files(project_path: Path, issues: list[QualityIssue]) -> dict[str, bool]:
    presence: dict[str, bool] = {}
    for relative in QUALITY_INPUTS:
        path = project_path / relative
        exists = path.exists()
        presence[relative] = exists
        if not exists:
            issues.append(QualityIssue("error", "required_artifact_missing", f"Required quality input is missing: {relative}", relative))
        elif path.is_file() and path.stat().st_size == 0:
            issues.append(QualityIssue("error", "required_artifact_empty", f"Required quality input is empty: {relative}", relative))
    return presence


def _check_project_validation(project: str | Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = validate_project(project)
    if report.get("status") != "passed":
        issues.append(QualityIssue("error", "project_validation_failed", "Project metadata or stage manifests failed validation.", "project.json"))
    return report


def _check_stage_readiness(state_meta: dict[str, Any], issues: list[QualityIssue]) -> dict[str, Any]:
    stages = state_meta.get("stages") or {}
    stale = []
    not_ready = []
    for stage in FINAL_INPUT_STAGES:
        stage_meta = stages.get(stage) or {}
        if stage_meta.get("stale"):
            stale.append(stage)
            issues.append(QualityIssue("error", "stale_stage_in_final_latex", f"Final LaTeX depends on stale stage: {stage}.", f"{stage}/stage_manifest.json"))
        if stage_meta.get("status") not in {"draft", "approved", "completed"}:
            not_ready.append(stage)
            issues.append(QualityIssue("error", "stage_not_ready_for_quality_gate", f"Stage is not ready for quality gate: {stage}={stage_meta.get('status')}.", f"{stage}/stage_manifest.json"))
    return {"stale_stages": stale, "not_ready_stages": not_ready}


def _check_methods(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    requirements = _read_json(project_path / "methods" / "method_requirements.json")
    if not requirements:
        issues.append(QualityIssue("error", "method_requirements_missing", "methods/method_requirements.json is required.", "methods/method_requirements.json"))
    manifest_path = project_path / "methods" / "run_manifest.yaml"
    manifest = _read_json(manifest_path)
    status = manifest.get("status")
    if status != "success":
        issues.append(QualityIssue("error", "methods_run_manifest_not_success", "methods/run_manifest.yaml must have status=success.", "methods/run_manifest.yaml"))
    missing_outputs = []
    for relative in manifest.get("output_files") or []:
        path = _project_relative_path(project_path, str(relative), issues, code="method_output_path_escape")
        if path and not path.exists():
            missing_outputs.append(str(relative))
            issues.append(QualityIssue("error", "method_output_missing", f"Declared method output is missing: {relative}", str(relative)))
    return {
        "method_data_fit": requirements.get("method_data_fit"),
        "primary_metric": requirements.get("primary_metric"),
        "minimum_primary_metric": requirements.get("minimum_primary_metric"),
        "run_manifest_status": status,
        "declared_output_count": len(manifest.get("output_files") or []),
        "missing_outputs": missing_outputs,
    }


def _check_result_validity(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "results" / "result_validity_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        issues.append(QualityIssue(
            "error",
            "result_validity_not_passed",
            f"Result validity must be pass or conditional_pass before final quality check. Current decision: {decision}.",
            "results/result_validity_report.json",
        ))
    if decision == "conditional_pass":
        issues.append(QualityIssue(
            "warning",
            "result_validity_conditional",
            "Results support only a reduced or threshold-unspecified claim level.",
            "results/result_validity_report.json",
        ))
    return {
        "decision": decision,
        "primary_metric": report.get("primary_metric"),
        "observed_value": report.get("observed_value"),
        "minimum_value": report.get("minimum_value"),
        "failure_causes": report.get("failure_causes") or [],
    }


def _check_core_evidence(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "core_evidence" / "core_evidence_report.json")
    decision = report.get("decision")
    if decision != "pass":
        issues.append(QualityIssue(
            "error",
            "core_evidence_not_passed",
            f"Core evidence must pass before final manuscript quality check. Current decision: {decision}.",
            "core_evidence/core_evidence_report.json",
        ))
    if not report.get("requires_user_confirmation", True):
        issues.append(QualityIssue(
            "warning",
            "core_evidence_confirmation_not_explicit",
            "Core evidence report should preserve an explicit human confirmation point for result figures.",
            "core_evidence/core_evidence_report.json",
        ))
    coverage = report.get("workflow_coverage") or {}
    missing = [key for key in ["data_supplementation", "data_integration", "method_analysis", "figure_production", "result_validity"] if not coverage.get(key)]
    if missing:
        issues.append(QualityIssue(
            "error",
            "core_evidence_workflow_coverage_incomplete",
            "Core evidence workflow coverage is incomplete: " + ", ".join(missing),
            "core_evidence/core_evidence_report.json",
        ))
    contract_coverage = report.get("figure_contract_coverage") or {}
    if contract_coverage and not contract_coverage.get("all_main_contracts_satisfied"):
        issues.append(QualityIssue(
            "error",
            "main_figure_contracts_not_satisfied",
            "Research-plan main figure contracts must be satisfied before final quality check; repair missing data or method code instead of substituting figures.",
            "core_evidence/core_evidence_report.json",
        ))
    return {
        "decision": decision,
        "figure_count": report.get("figure_count"),
        "workflow_coverage": coverage,
        "figure_contract_coverage": contract_coverage,
        "requires_user_confirmation": report.get("requires_user_confirmation"),
    }


def _check_data_feasibility(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "data" / "data_feasibility_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        issues.append(QualityIssue(
            "error",
            "data_feasibility_not_passed",
            f"Data feasibility must be pass or conditional_pass before final quality check. Current decision: {decision}.",
            "data/data_feasibility_report.json",
        ))
    if decision == "conditional_pass":
        issues.append(QualityIssue(
            "warning",
            "data_feasibility_conditional",
            "Data supports only a reduced or exploratory claim level.",
            "data/data_feasibility_report.json",
        ))
    return {
        "decision": decision,
        "scientific_goal_supported": report.get("scientific_goal_supported"),
        "supported_claim_level": report.get("supported_claim_level"),
        "blocking_issue_count": len(report.get("blocking_issues") or []),
    }


def _check_manuscript_narrative_hygiene(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    data_tex = _read_text(project_path / "data" / "data.tex")
    methods_tex = _read_text(project_path / "methods" / "methods.tex")
    data_matches = FILESYSTEM_PATTERN.findall(data_tex)
    method_filesystem_matches = FILESYSTEM_PATTERN.findall(methods_tex)
    method_execution_matches = METHOD_EXECUTION_PATTERN.findall(methods_tex)
    if data_matches:
        issues.append(QualityIssue(
            "error",
            "data_contains_filesystem_reference",
            "Data section should describe source, content, variables, processing, and claim boundaries rather than local filenames or paths.",
            "data/data.tex",
        ))
    if method_filesystem_matches or method_execution_matches:
        issues.append(QualityIssue(
            "error",
            "methods_contains_execution_or_filesystem_reference",
            "Methods section should describe the scientific workflow rather than local commands, paths, filenames, or manifest internals.",
            "methods/methods.tex",
        ))
    return {
        "data_filesystem_reference_count": len(data_matches),
        "methods_filesystem_reference_count": len(method_filesystem_matches),
        "methods_execution_reference_count": len(method_execution_matches),
    }


def _check_results(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    results_tex = _read_text(project_path / "results" / "results.tex")
    citation_count = 1 if has_citation_command(results_tex) else 0
    if citation_count:
        issues.append(QualityIssue("error", "results_contains_citation", "Results section must not contain citation commands.", "results/results.tex"))

    manifest = _read_json(project_path / "results" / "result_manifest.yaml")
    figure_plan = _read_json(project_path / "results" / "figure_plan.json")
    figure_metadata = _read_json(project_path / "results" / "figure_metadata.json")
    figure_quality = _read_json(project_path / "results" / "figure_quality_report.json")
    metadata_by_path = {
        str(item.get("path") or ""): item
        for item in figure_metadata.get("figures") or []
        if item.get("path")
    }
    generated_figure_paths = {
        str(item.get("path") or "")
        for item in figure_plan.get("figures") or []
        if item.get("generation_mode") == "generated_code" and item.get("path")
    }
    if generated_figure_paths and figure_quality.get("status") == "failed":
        issues.append(QualityIssue("error", "scientific_figure_quality_failed", "Scientific figure quality report failed.", "results/figure_quality_report.json"))
    if generated_figure_paths and not metadata_by_path:
        issues.append(QualityIssue("error", "figure_metadata_missing", "Generated empirical result figures require results/figure_metadata.json.", "results/figure_metadata.json"))
    entries = []
    for item in manifest.get("figures") or []:
        entries.append(("figure", item))
    for item in manifest.get("tables") or []:
        entries.append(("table", item))
    if not entries:
        issues.append(QualityIssue("error", "result_manifest_empty", "results/result_manifest.yaml must declare at least one figure or table.", "results/result_manifest.yaml"))

    missing = []
    escaping = []
    for kind, entry in entries:
        relative = str(entry.get("path") or "")
        if not relative:
            issues.append(QualityIssue("error", "result_artifact_path_missing", f"A {kind} result entry has no path.", "results/result_manifest.yaml"))
            continue
        path = _project_relative_path(project_path, relative, issues, code="result_artifact_path_escape")
        if path and not path.exists():
            missing.append(relative)
            issues.append(QualityIssue("error", "result_artifact_missing", f"Declared result artifact is missing: {relative}", relative))
        if kind == "figure" and relative in generated_figure_paths:
            metadata = metadata_by_path.get(relative)
            if not metadata:
                issues.append(QualityIssue("error", "figure_metadata_entry_missing", f"Figure lacks scientific metadata: {relative}", "results/figure_metadata.json"))
            elif (
                metadata.get("is_placeholder")
                or metadata.get("file_format") != "png"
                or not metadata.get("has_axes")
                or not metadata.get("axis_labels")
                or not metadata.get("text_elements")
                or not metadata.get("figure_size_inches")
                or not metadata.get("publication_ready")
                or not metadata.get("statistics")
                or not metadata.get("interpretation_summary")
            ):
                issues.append(QualityIssue("error", "figure_metadata_not_scientific", f"Figure metadata does not satisfy scientific-result requirements: {relative}", "results/figure_metadata.json"))
        text = " ".join(str(entry.get(key) or "") for key in ("caption_draft", "result_claim"))
        if has_citation_command(text):
            issues.append(QualityIssue("error", "result_manifest_contains_citation", "Results manifest contains a citation command.", "results/result_manifest.yaml"))
    return {
        "artifact_count": len(entries),
        "missing_artifacts": missing,
        "citation_command_count": citation_count,
        "subsection_count": results_tex.count("\\subsection"),
        "path_escape_count": len(escaping),
        "figure_metadata_count": len(metadata_by_path),
        "figure_quality_status": figure_quality.get("status"),
    }


def _check_manuscript_writing_quality(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    section_files = {
        "introduction": project_path / "introduction" / "introduction.tex",
        "data": project_path / "data" / "data.tex",
        "methods": project_path / "methods" / "methods.tex",
        "results": project_path / "results" / "results.tex",
        "discussion": project_path / "discussion" / "discussion.tex",
    }
    manifest = _read_json(project_path / "results" / "result_manifest.yaml")
    figure_count = len(manifest.get("figures") or [])
    report: dict[str, Any] = {}
    for section, path in section_files.items():
        tex = _read_text(path)
        section_issues = evaluate_section_quality(
            section,
            tex,
            figure_count=figure_count if section == "results" else None,
        )
        report[section] = {
            "issue_count": len(section_issues),
            "issue_codes": [issue.code for issue in section_issues],
        }
        for issue in section_issues:
            issues.append(QualityIssue(issue.severity, issue.code, issue.message, str(path.relative_to(project_path))))
    return report


def _check_bibliography(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    main_tex = _read_text(project_path / "latex" / "main.tex")
    bibtex = _read_text(project_path / "latex" / "library.bib")
    introduction_tex = _read_text(project_path / "introduction" / "introduction.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "introduction.tex")
    data_tex = _read_text(project_path / "data" / "data.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "data.tex")
    methods_tex = _read_text(project_path / "methods" / "methods.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "methods.tex")
    discussion_tex = _read_text(project_path / "discussion" / "discussion.tex") + "\n" + _read_text(project_path / "latex" / "sections" / "discussion.tex")
    section_tex = "\n".join([introduction_tex, data_tex, methods_tex, discussion_tex])
    bib_keys = _bibtex_keys(bibtex)
    main_citations = _latex_citation_keys(main_tex + "\n" + section_tex)
    intro_discussion_citations = _latex_citation_keys(introduction_tex + "\n" + discussion_tex)
    all_section_citations = _latex_citation_keys(section_tex)
    evidence_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    evidence_keys = {row.get("citation_key", "") for row in evidence_rows if row.get("citation_key")}
    evidence_by_section: dict[str, set[str]] = {}
    for row in evidence_rows:
        section = (row.get("section") or "").strip().lower()
        key = (row.get("citation_key") or "").strip()
        if section and key:
            evidence_by_section.setdefault(section, set()).add(key)

    if not bib_keys:
        issues.append(QualityIssue("error", "bib_no_entries", "latex/library.bib contains no BibTeX entries.", "latex/library.bib"))
    missing = sorted(main_citations - bib_keys)
    if missing:
        issues.append(QualityIssue("error", "citation_key_missing", "LaTeX cites keys that are absent from BibTeX: " + ", ".join(missing[:12]), "latex/main.tex"))
    untraced = sorted(intro_discussion_citations - evidence_keys)
    if untraced:
        issues.append(QualityIssue("error", "citation_not_in_evidence_table", "Introduction/Discussion cite keys absent from citation_evidence.csv: " + ", ".join(untraced[:12]), "references/citation_evidence.csv"))
    if "\\bibliography{" not in main_tex:
        issues.append(QualityIssue("error", "bibliography_command_missing", "latex/main.tex has no bibliography command.", "latex/main.tex"))
    if "natbib" not in main_tex and main_citations:
        issues.append(QualityIssue("warning", "natbib_missing", "latex/main.tex cites literature but does not load natbib.", "latex/main.tex"))
    section_citation_report = {}
    for section, tex, file_name in [
        ("data", data_tex, "data/data.tex"),
        ("methods", methods_tex, "methods/methods.tex"),
    ]:
        expected_keys = evidence_by_section.get(section, set())
        cited_keys = _latex_citation_keys(tex)
        matched_keys = sorted(expected_keys & cited_keys)
        section_citation_report[section] = {
            "evidence_key_count": len(expected_keys),
            "matched_citation_count": len(matched_keys),
            "matched_citation_keys": matched_keys,
        }
        if expected_keys and not matched_keys:
            issues.append(QualityIssue(
                "warning",
                f"{section}_context_references_not_cited",
                f"citation_evidence.csv contains {section}-context references, but the {section.capitalize()} section cites none of them.",
                file_name,
            ))
    unused_bib_keys = sorted(bib_keys - all_section_citations)
    if unused_bib_keys:
        issues.append(QualityIssue("warning", "bib_entries_not_used_in_manuscript", "BibTeX entries not cited in the assembled manuscript sections: " + ", ".join(unused_bib_keys[:12]), "latex/library.bib"))
    return {
        "bibtex_entry_count": len(bib_keys),
        "latex_citation_count": len(main_citations),
        "intro_discussion_citation_count": len(intro_discussion_citations),
        "missing_citation_keys": missing,
        "citations_without_evidence": untraced,
        "unused_bibtex_keys": unused_bib_keys,
        "section_context_citations": section_citation_report,
    }


def _check_citation_audit(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    report = _read_json(project_path / "citation_audit" / "final_citation_audit_report.json")
    coverage_report = _read_json(project_path / "citation_audit" / "reference_coverage_report.json")
    status = report.get("status")
    summary = report.get("summary") or {}
    coverage = report.get("reference_coverage") or coverage_report or {}
    if status != "passed":
        issues.append(QualityIssue(
            "error",
            "citation_audit_not_passed",
            "Final quality check requires citation_audit/final_citation_audit_report.json with status=passed.",
            "citation_audit/final_citation_audit_report.json",
        ))
    blocking = int(summary.get("blocking_issue_count") or 0)
    if blocking:
        issues.append(QualityIssue(
            "error",
            "citation_audit_has_blocking_issues",
            f"Final citation audit still has blocking source-support issues: {blocking}.",
            "citation_audit/final_citation_audit_report.json",
        ))
    if coverage and coverage.get("coverage_status") == "failed":
        missing = int(coverage.get("summarized_but_uncited_count") or 0)
        issues.append(QualityIssue(
            "error",
            "citation_reference_coverage_failed",
            (
                f"Citation audit preserves the retained reference library, but {missing} summarized reference(s) are still uncited. "
                "Revise Introduction, Data, Methods, or Discussion to use the retained references accurately instead of deleting them."
            ),
            "citation_audit/reference_coverage_report.json",
        ))
    return {
        "status": status,
        "blocking_issue_count": blocking,
        "reference_coverage_status": coverage.get("coverage_status"),
        "summarized_reference_count": coverage.get("summarized_reference_count"),
        "unique_cited_reference_count": coverage.get("unique_cited_reference_count"),
        "summarized_but_uncited_count": coverage.get("summarized_but_uncited_count"),
        "average_match_score": summary.get("average_match_score"),
        "unsupported": summary.get("unsupported"),
        "unverifiable": summary.get("unverifiable"),
    }


def _check_latex_hygiene(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    main_tex = _read_text(project_path / "latex" / "main.tex")
    profile = _read_json(project_path / "journal_profile" / "journal_profile.json")
    documentclass = str(profile.get("documentclass") or "")
    target_journal = str(profile.get("target_journal") or "")
    begin_doc = main_tex.count("\\begin{document}")
    end_doc = main_tex.count("\\end{document}")
    if begin_doc != 1 or end_doc != 1:
        issues.append(QualityIssue("error", "latex_document_environment_invalid", f"Expected one document environment, found begin={begin_doc}, end={end_doc}.", "latex/main.tex"))
    if "\\input{sections/results}" not in main_tex:
        issues.append(QualityIssue("error", "latex_results_input_missing", "latex/main.tex does not input sections/results.", "latex/main.tex"))
    if documentclass and f"{{{documentclass}}}" not in main_tex:
        issues.append(QualityIssue("error", "journal_documentclass_not_used", f"latex/main.tex does not use journal documentclass: {documentclass}.", "latex/main.tex"))
    if "aastex" in documentclass.lower():
        if "\\submitjournal{" not in main_tex:
            issues.append(QualityIssue("error", "aas_submitjournal_missing", "AAS templates require a submitjournal command.", "latex/main.tex"))
        if "\\keywords{" not in main_tex:
            issues.append(QualityIssue("warning", "aas_keywords_missing", "AAS templates expect UAT keywords.", "latex/main.tex"))
        if "\\bibliographystyle{aasjournal}" not in main_tex and "\\bibliographystyle{aasjournalv7}" not in main_tex:
            issues.append(QualityIssue("error", "aas_bibliography_style_missing", "AAS templates should use an AAS journal bibliography style.", "latex/main.tex"))
    inline_dollars = re.sub(r"\\\$", "", main_tex).count("$")
    if inline_dollars % 2 != 0:
        issues.append(QualityIssue("error", "unbalanced_inline_math", "latex/main.tex has an odd number of inline math delimiters.", "latex/main.tex"))
    return {
        "document_begin_count": begin_doc,
        "document_end_count": end_doc,
        "inline_dollar_count": inline_dollars,
        "journal_documentclass": documentclass,
        "target_journal": target_journal,
    }


def _check_pdf(project_path: Path, issues: list[QualityIssue]) -> dict[str, Any]:
    manifest_path = project_path / "latex" / "pdf_compile_manifest.json"
    pdf_path = project_path / "latex" / "main.pdf"
    if not manifest_path.exists():
        return {"status": "not_run", "pdf_exists": pdf_path.exists()}
    manifest = _read_json(manifest_path)
    status = manifest.get("status")
    if status == "failed":
        issues.append(QualityIssue("error", "pdf_compile_failed", str(manifest.get("message") or "PDF compilation failed."), "latex/pdf_compile_manifest.json"))
    elif status == "skipped":
        issues.append(QualityIssue("warning", "pdf_compile_skipped", str(manifest.get("message") or "PDF compilation skipped."), "latex/pdf_compile_manifest.json"))
    elif status == "success" and not pdf_path.exists():
        issues.append(QualityIssue("error", "pdf_missing_after_success", "PDF manifest says success but latex/main.pdf is missing.", "latex/main.pdf"))
    return {"status": status, "pdf_exists": pdf_path.exists(), "manifest": str(manifest_path)}


def _set_quality_manifest(project_path: Path) -> None:
    manifest_path = project_path / "quality_checks" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = QUALITY_INPUTS
    manifest["output_files"] = QUALITY_OUTPUTS
    _write_json(manifest_path, manifest)


def run_quality_check(project: str | Path) -> dict[str, Any]:
    """Run final staged manuscript quality checks and write quality_checks/quality_report.json."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise QualityGateError(str(exc)) from exc

    issues: list[QualityIssue] = []
    validation = _check_project_validation(state.path, issues)
    required_files = _check_required_files(state.path, issues)
    stage_report = _check_stage_readiness(state.metadata, issues)
    data_report = _check_data_feasibility(state.path, issues)
    methods_report = _check_methods(state.path, issues)
    result_validity_report = _check_result_validity(state.path, issues)
    core_evidence_report = _check_core_evidence(state.path, issues)
    results_report = _check_results(state.path, issues)
    manuscript_hygiene_report = _check_manuscript_narrative_hygiene(state.path, issues)
    writing_quality_report = _check_manuscript_writing_quality(state.path, issues)
    bibliography_report = _check_bibliography(state.path, issues)
    citation_audit_report = _check_citation_audit(state.path, issues)
    latex_report = _check_latex_hygiene(state.path, issues)
    pdf_report = _check_pdf(state.path, issues)

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
        "project": {
            "project_id": state.metadata.get("project_id"),
            "validation_status": validation.get("status"),
            "required_files_present": required_files,
        },
        "stages": stage_report,
        "data": data_report,
        "methods": methods_report,
        "result_validity": result_validity_report,
        "core_evidence": core_evidence_report,
        "results": results_report,
        "manuscript_hygiene": manuscript_hygiene_report,
        "writing_quality": writing_quality_report,
        "bibliography": bibliography_report,
        "citation_audit": citation_audit_report,
        "latex": latex_report,
        "pdf": pdf_report,
    }

    quality_dir = state.path / "quality_checks"
    quality_dir.mkdir(parents=True, exist_ok=True)
    _write_json(quality_dir / "quality_report.json", report)
    update_stage_status(state.path, "quality_checks", "draft" if status == "passed" else "failed")
    _set_quality_manifest(state.path)
    return report
