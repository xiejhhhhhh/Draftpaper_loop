# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path, payload):
    _write(path, json.dumps(payload))



def _quality_architecture(project):
    _json(project / "writing" / "paper_brief.json", {"paper": "brief"})
    _json(project / "writing" / "argument_matrices.json", {
        "introduction_gap_matrix": [{"gap_id": "g1"}],
        "discussion_finding_comparison_matrix": [{"comparison_id": "c1"}],
    })
    _json(project / "writing" / "section_lifecycles.json", {"data_lifecycle": {}, "method_lifecycle": {}})
    _json(project / "results" / "panel_figure_contracts.json", {"figure_groups": [{"figure_group_id": "f1"}]})
    _json(project / "writing" / "scientific_evidence_registry.json", {"records": [], "blocking_conflicts": []})
    _json(project / "quality_checks" / "blind_manuscript_evaluation.json", {
        "schema_version": "dpl.independent_review_aggregate.v1",
        "status": "passed",
        "reviewer_count": 2,
        "frozen_submission_bundle_hash": "bundle-1",
        "release_review_status": "pass",
        "critical_open_count": 0,
        "major_open_count": 0,
        "adjudication_required": False,
        "score_means": {"scientific_correctness": 0.97},
        "revision_queue": [],
        "relative_quality_ratio_prohibited": True,
    })
    for section in ("introduction", "data", "methods", "results", "discussion"):
        _json(project / "writing" / "section_validation" / f"{section}.json", {
            "generated_at": "2026-07-12T10:00:00+00:00",
            "decision": "pass",
            "composition_mode": "codex_free_candidate",
            "quality_parity_eligible": True,
            "evidence_snapshot_id": "snapshot-1",
            "functional_job_coverage": {"decision": "pass", "score": 1.0},
        })

def test_full_paper_quality_parity_passes_complete_scientific_manuscript(tmp_path) -> None:
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _write(project / "introduction" / "introduction.tex", r"The scientific problem remains unresolved \cite{A}. Prior work leaves a validation gap \cite{B}. We therefore test the hypothesis that the proposed representation improves generalization \cite{C}.")
    _write(project / "data" / "data.tex", "The data source defines a cohort of 120 samples. Processing harmonized the measurements, quantified missingness, and retained the declared coverage boundary.")
    _write(project / "methods" / "methods.tex", r"The model maps features to probabilities. \begin{equation}p_i=\sigma(f(x_i))\end{equation} where x_i denotes the feature vector and p_i is the predicted probability. Validation uses a held-out split, a baseline comparison, and an ablation study.")
    _write(project / "results" / "results.tex", "The verified Results interpret five figures and report only run-bound evidence.")
    _write(project / "discussion" / "discussion.tex", r"Compared with prior work \cite{A}, the result clarifies the mechanism. The main innovation is the validated integration of evidence. A limitation is the current cohort size, which motivates external validation.")
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _quality_architecture(project)
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "generated_at": "2026-07-12T11:00:00+00:00", "status": "passed",
        "summary": {"blocking_issue_count": 0},
        "reference_coverage": {"coverage_status": "passed", "summarized_but_uncited_count": 0, "coverage_ratio": 1.0},
    })

    report = assess_paper_quality_parity(project)

    assert report["score"] >= 0.95
    assert report["decision"] == "pass"


def test_full_paper_quality_parity_exposes_thin_sections(tmp_path) -> None:
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _write(project / "introduction" / "introduction.tex", "This topic is important.")
    _write(project / "data" / "data.tex", "Data were used.")
    _write(project / "methods" / "methods.tex", "A model was trained.")
    _write(project / "results" / "results.tex", "Results are shown.")
    _write(project / "discussion" / "discussion.tex", "The method works.")
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "repair_required", "score": 0.4})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "repair_required", "score": 0.3})

    report = assess_paper_quality_parity(project)

    assert report["score"] < 0.5
    assert report["decision"] == "repair_required"
    assert report["hard_correctness_passed"] is False
    assert report["repair_priorities"]

def test_quality_parity_rejects_deterministic_section_fallback(tmp_path) -> None:
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _quality_architecture(project)
    fallback_path = project / "writing" / "section_validation" / "methods.json"
    fallback_report = json.loads(fallback_path.read_text(encoding="utf-8"))
    fallback_report.update({
        "composition_mode": "deterministic_offline_fallback",
        "quality_parity_eligible": False,
    })
    _json(fallback_path, fallback_report)
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "generated_at": "2026-07-12T11:00:00+00:00",
        "status": "passed",
        "summary": {"blocking_issue_count": 0},
        "reference_coverage": {"coverage_status": "passed", "summarized_but_uncited_count": 0, "coverage_ratio": 1.0},
    })

    report = assess_paper_quality_parity(project)

    assert report["decision"] == "repair_required"
    assert report["hard_checks"]["all_core_sections_validated_free_prose"] is False
    assert report["hard_correctness_passed"] is False


def test_quality_parity_requires_citation_audit_after_final_section_validation(tmp_path) -> None:
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _quality_architecture(project)
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "generated_at": "2026-07-12T09:59:59+00:00",
        "status": "passed",
        "summary": {"blocking_issue_count": 0},
        "reference_coverage": {"coverage_status": "passed", "summarized_but_uncited_count": 0, "coverage_ratio": 1.0},
    })

    report = assess_paper_quality_parity(project)

    assert report["decision"] == "repair_required"
    assert report["hard_checks"]["citation_audit_after_final_draft"] is False
    assert report["hard_correctness_passed"] is False


def test_quality_parity_accepts_current_citation_audit_snapshot_without_section_timestamps(tmp_path) -> None:
    from draftpaper_cli.evidence_snapshot import manuscript_snapshot
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _write(project / "introduction" / "introduction.tex", "Introduction")
    _write(project / "data" / "data.tex", "Data")
    _write(project / "methods" / "methods.tex", "Methods")
    _write(project / "results" / "results.tex", "Results")
    _write(project / "discussion" / "discussion.tex", "Discussion")
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _quality_architecture(project)
    for section in ("introduction", "data", "methods", "results", "discussion"):
        report_path = project / "writing" / "section_validation" / f"{section}.json"
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        payload.pop("generated_at", None)
        _json(report_path, payload)
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "status": "passed",
        "summary": {"blocking_issue_count": 0},
        "reference_coverage": {"coverage_status": "passed", "summarized_but_uncited_count": 0, "coverage_ratio": 1.0},
        "manuscript_snapshot": manuscript_snapshot(project),
    })

    report = assess_paper_quality_parity(project)

    assert report["hard_checks"]["citation_audit_after_final_draft"] is True


def test_quality_parity_requires_two_independent_single_manuscript_reviews(tmp_path) -> None:
    from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _quality_architecture(project)
    (project / "quality_checks" / "blind_manuscript_evaluation.json").unlink()
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "generated_at": "2026-07-12T11:00:00+00:00", "status": "passed",
        "summary": {"blocking_issue_count": 0},
        "reference_coverage": {"coverage_status": "passed", "summarized_but_uncited_count": 0, "coverage_ratio": 1.0},
    })

    report = assess_paper_quality_parity(project)

    assert report["decision"] == "repair_required"
    assert report["functional_quality_score"] >= 0.95
    assert report["automated_functional_quality_score"] >= 0.95
    assert report["hard_checks"]["two_independent_single_manuscript_reviews_passed"] is False
