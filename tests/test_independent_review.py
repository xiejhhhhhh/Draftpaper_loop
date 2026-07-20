from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from draftpaper_cli.independent_review import (
    IndependentReviewError,
    SCORE_DIMENSIONS,
    assess_manuscript_quality_release,
    prepare_independent_manuscript_review,
    record_independent_manuscript_review,
    _anonymize_review_tex,
)
from draftpaper_cli.project_scaffold import create_project


def _project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Independent review", field="engineering").path
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with (project / "latex" / "main.pdf").open("wb") as handle:
        writer.write(handle)
    (project / "latex" / "main.tex").write_text(
        "\\documentclass{article}\n\\author{Anonymous manuscript}\n\\begin{document}\nAnonymous text.\\end{document}\n",
        encoding="utf-8",
    )
    (project / "latex" / "sections" / "results.tex").write_text("Results text.\n", encoding="utf-8")
    (project / "results" / "figures" / "figure_1.png").write_bytes(b"figure")
    (project / "results" / "tables" / "table_1.csv").write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    (project / "references" / "library.bib").write_text("@article{A,title={A}}\n", encoding="utf-8")
    (project / "references" / "reference_registry.json").write_text(
        json.dumps({"status": "passed", "references": ["A"]}), encoding="utf-8"
    )
    (project / "results" / "promoted_evidence_snapshot.json").write_text(
        json.dumps({"snapshot_id": "evidence:review", "artifacts": {}}), encoding="utf-8"
    )
    (project / "core_evidence" / "core_evidence_report.json").write_text(
        json.dumps({"decision": "pass"}), encoding="utf-8"
    )
    return project


def _report(bundle_hash: str, session: str, recommendation: str = "minor_revision", findings: list[dict] | None = None) -> dict:
    if findings is None:
        findings = [{
            "severity": "advisory",
            "locator": "page 1, Results, Figure 1",
            "detail": "The result summary is grounded in the frozen manuscript.",
            "required_action": "Retain the current evidence boundary.",
        }]
    return {
        "frozen_submission_bundle_hash": bundle_hash,
        "independent_session_provider_id_hash": session,
        "overall_recommendation": recommendation,
        "scores": {name: 0.95 for name in SCORE_DIMENSIONS},
        "findings": findings,
        "strengths": ["The evidence chain is visible."],
        "weaknesses": [],
        "required_revisions": [],
        "confidence": "high",
        "checked_real_figures": True,
        "full_manuscript_reviewed": True,
    }


def test_two_reviewers_inspect_one_frozen_generated_manuscript_without_baseline(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prepared = prepare_independent_manuscript_review(project)
    manifest = json.loads((project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json").read_text(encoding="utf-8"))
    zip_path = project / prepared["bundle"]
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        frozen_records = [
            record
            for group in manifest["frozen_artifacts"].values()
            for record in group
        ]
        assert names == {"bundle_manifest.json", *(record["path"] for record in frozen_records)}
        for record in frozen_records:
            payload = archive.read(record["path"])
            assert __import__("hashlib").sha256(payload).hexdigest() == record["sha256"]
            assert len(payload) == record["size_bytes"]
    assert {
        "latex/main.pdf",
        "latex/main.tex",
        "latex/sections/results.tex",
        "references/library.bib",
        "references/reference_registry.json",
        "results/promoted_evidence_snapshot.json",
        "core_evidence/core_evidence_report.json",
    }.issubset(names)
    assert not any("baseline" in name.lower() or "original" in name.lower() for name in names)
    assert not any("quality_report" in name.lower() or "audit" in name.lower() for name in names)
    assert "not the ZIP container byte hash" in manifest["bundle_hash_semantics"]

    for slot, session in (("reviewer_01", "session-hash-1"), ("reviewer_02", "session-hash-2")):
        path = tmp_path / f"{slot}.json"
        path.write_text(json.dumps(_report(prepared["bundle_hash"], session)), encoding="utf-8")
        record_independent_manuscript_review(project, slot, path)

    aggregate = assess_manuscript_quality_release(project)
    assert aggregate["status"] == "passed"
    assert aggregate["reviewer_count"] == 2
    assert aggregate["relative_quality_ratio_prohibited"] is True
    assert "quality_ratio" not in aggregate
    assert aggregate["reviewer_report_sha256"] == {
        relative: __import__("hashlib").sha256((project / relative).read_bytes()).hexdigest()
        for relative in aggregate["reviewer_reports"]
    }


@pytest.mark.parametrize("findings", [None, [], ["not-a-structured-finding"]])
def test_independent_report_requires_grounded_structured_findings(tmp_path: Path, findings: object) -> None:
    project = _project(tmp_path)
    prepared = prepare_independent_manuscript_review(project)
    payload = _report(prepared["bundle_hash"], "session-1")
    if findings is None:
        payload.pop("findings")
    else:
        payload["findings"] = findings
    path = tmp_path / "incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(IndependentReviewError, match="grounded finding"):
        record_independent_manuscript_review(project, "reviewer_01", path)


def test_independent_report_returns_domain_finding_for_overflowing_numeric_score(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prepared = prepare_independent_manuscript_review(project)
    payload = _report(prepared["bundle_hash"], "session-1")
    payload["scores"][next(iter(SCORE_DIMENSIONS))] = 10**1000
    path = tmp_path / "overflowing-score.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(IndependentReviewError, match="score is not numeric"):
        record_independent_manuscript_review(project, "reviewer_01", path)


def test_review_bundle_includes_locator_safe_reproducibility_support(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "data" / "source_provenance.json").write_text(
        json.dumps({"release": "survey-r1", "selection": "quality-selected cohort"}), encoding="utf-8"
    )
    (project / "methods" / "model_provenance.json").write_text(
        json.dumps({"checkpoint_identifier": "official-model", "weight_checksum": None}), encoding="utf-8"
    )
    script = project / "methods" / "scripts" / "run_analysis.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('reproducible analysis')\n", encoding="utf-8")

    prepared = prepare_independent_manuscript_review(project)

    with zipfile.ZipFile(project / prepared["bundle"]) as archive:
        names = set(archive.namelist())
    assert "data/source_provenance.json" in names
    assert "methods/model_provenance.json" in names
    assert "methods/scripts/run_analysis.py" in names


def test_review_bundle_excludes_reproducibility_file_with_private_locator(tmp_path: Path) -> None:
    project = _project(tmp_path)
    script = project / "methods" / "scripts" / "run_analysis.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("SOURCE = r'C:\\private\\cohort.csv'\n", encoding="utf-8")

    prepared = prepare_independent_manuscript_review(project)
    manifest = json.loads((project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json").read_text(encoding="utf-8"))

    with zipfile.ZipFile(project / prepared["bundle"]) as archive:
        names = set(archive.namelist())
    assert "methods/scripts/run_analysis.py" not in names
    assert manifest["excluded_reproducibility_files"] == [
        {"path": "methods/scripts/run_analysis.py", "reason": "private_locator_or_credential_pattern"}
    ]


def test_independent_report_rejects_original_or_quality_ratio_fields(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prepared = prepare_independent_manuscript_review(project)
    payload = _report(prepared["bundle_hash"], "session-1")
    payload["baseline_manuscript_hash"] = "forbidden"
    payload["quality_ratio"] = 0.95
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(IndependentReviewError, match="prohibited"):
        record_independent_manuscript_review(project, "reviewer_01", path)


def test_critical_finding_or_large_disagreement_requires_adjudication(tmp_path: Path) -> None:
    project = _project(tmp_path)
    prepared = prepare_independent_manuscript_review(project)
    critical = [{
        "severity": "critical",
        "locator": "page 1, Results, Figure 1",
        "detail": "The reported cohort conflicts with the figure denominator.",
        "required_action": "Reconcile the cohort and regenerate the affected section.",
    }]
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps(_report(prepared["bundle_hash"], "session-a", "not_ready", critical)), encoding="utf-8")
    second.write_text(json.dumps(_report(prepared["bundle_hash"], "session-b", "minor_revision")), encoding="utf-8")
    record_independent_manuscript_review(project, "reviewer_01", first)
    record_independent_manuscript_review(project, "reviewer_02", second)

    aggregate = assess_manuscript_quality_release(project)
    assert aggregate["status"] == "adjudication_required"
    assert aggregate["critical_open_count"] == 1
    assert aggregate["release_review_status"] == "blocked"


def test_review_bundle_rejects_visible_declared_author_identity(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "writing" / "manuscript_metadata.json").write_text(
        json.dumps({"authors": [{"name": "Visible Author"}]}), encoding="utf-8"
    )
    # A malformed/non-extractable PDF is treated conservatively when identity is declared.
    (project / "latex" / "main.pdf").write_bytes(b"not-a-pdf")
    with pytest.raises(IndependentReviewError, match="contains declared author identity"):
        prepare_independent_manuscript_review(project)


def test_review_bundle_accepts_explicit_anonymous_metadata(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "writing" / "manuscript_metadata.json").write_text(
        json.dumps({"authors": [{"name": "Anonymous Manuscript"}]}), encoding="utf-8"
    )

    prepared = prepare_independent_manuscript_review(project)

    assert prepared["status"] == "prepared"


def test_anonymous_review_tex_redacts_identity_and_preserves_front_matter_contract() -> None:
    rendered = _anonymize_review_tex(
        "\\documentclass{aastex701}\n"
        "\\begin{document}\n"
        "\\title{Study}\n"
        "\\author{Jinray Xie}\n"
        "\\affiliation{University}\n"
        "\\email{author@example.org}\n"
        "\\graphicspath{{../}}\n"
        "\\section{Introduction}\nText.\n"
        "\\end{document}\n"
    )

    assert "Jinray Xie" not in rendered
    assert "author@example.org" not in rendered
    assert "\\author{Anonymous Manuscript}" in rendered
    assert "\\affiliation{Withheld for anonymous review}" in rendered
    assert "\\email{withheld@anonymous.invalid}" in rendered
    assert "\\graphicspath{{../../../}}" in rendered
