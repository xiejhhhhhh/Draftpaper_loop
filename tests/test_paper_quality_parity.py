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
    _json(project / "citation_audit" / "final_citation_audit_report.json", {"decision": "pass", "blocking_issue_count": 0, "reference_coverage": {"coverage_ratio": 1.0}})

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
    assert {item["section"] for item in report["repair_priorities"]} >= {"figures", "results", "methods", "discussion"}
