# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _quality_project(tmp_path):
    project = create_project(root=tmp_path, idea="A classifier study", field="machine learning", target_journal="Test").path
    contracts = [
        {"figure_id": "fig_scope", "title": "Sample and modality coverage", "research_question": "What is the study boundary?", "expected_finding": "The cohort defines the supported scope."},
        {"figure_id": "fig_signal", "title": "Feature space before training", "research_question": "Is there pre-model signal?", "expected_finding": "Features show partial class separation."},
        {"figure_id": "fig_compare", "title": "Baseline versus proposed model performance", "research_question": "Does the model outperform baselines?", "expected_finding": "Ablation should later show which component drives the result."},
        {"figure_id": "fig_ablation", "title": "Ablation of feature blocks", "research_question": "Which components contribute?", "expected_finding": "Removing one component reduces performance."},
        {"figure_id": "fig_error", "title": "Error structure and uncertainty", "research_question": "Where is the model uncertain?", "expected_finding": "Intermediate scores identify uncertain cases."},
    ]
    _json(project / "results" / "figure_contracts.json", {"main_contracts": contracts})
    figures = [
        {"id": item["figure_id"], "path": f"results/figures/{item['figure_id']}.png", "caption_draft": item["title"], "scientific_question": item["research_question"], "result_claim": item["expected_finding"], "manuscript_role": "main"}
        for item in contracts
    ]
    _json(project / "results" / "result_manifest.yaml", {"main_figures": figures, "appendix_figures": [], "tables": []})
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run_1", "metrics": {
        "best_baseline_f1_macro": 0.8667,
        "proposed_model_f1_macro": 0.8053,
        "ablation_without_features_f1_macro": 0.7494,
    }})
    return project


def test_results_narrative_contract_assigns_distinct_scientific_roles(tmp_path) -> None:
    from draftpaper_cli.manuscript_quality import build_results_narrative_contract

    project = _quality_project(tmp_path)
    contract = build_results_narrative_contract(project)

    roles = {item["narrative_role"] for item in contract["figure_groups"]}
    assert {"study_boundary", "premodel_signal", "model_comparison", "component_attribution", "error_uncertainty"} <= roles
    comparison = next(item for item in contract["figure_groups"] if item["narrative_role"] == "model_comparison")
    assert {item["metric_name"] for item in comparison["verified_metrics"]} >= {"best_baseline_f1_macro", "proposed_model_f1_macro"}


def test_quality_scorer_rewards_evidence_driven_narrative(tmp_path) -> None:
    from draftpaper_cli.manuscript_quality import assess_results_manuscript_quality, build_results_narrative_contract

    project = _quality_project(tmp_path)
    contract = build_results_narrative_contract(project)
    text = r"""
    \section{Results}
    Figure~\ref{fig:fig-scope} fixes the study boundary and available modalities before model interpretation.
    Figure~\ref{fig:fig-signal} shows partial pre-model class separation, which supports supervised analysis but not a simple threshold rule.
    Under the declared validation split, Figure~\ref{fig:fig-compare} shows that the strongest baseline reached macro F1=0.8667, whereas the proposed model reached macro F1=0.8053. The model is therefore feasible but does not outperform the baseline.
    The ablation in Figure~\ref{fig:fig-ablation} reduced macro F1 to 0.7494 when the feature block was removed, identifying that block as a material contributor rather than assuming every branch helps.
    Figure~\ref{fig:fig-error} localizes the remaining errors and intermediate-score uncertainty. These cases define the practical review region and limit the conclusion to the current cohort and validation design.
    """

    report = assess_results_manuscript_quality(project, text=text, contract=contract)

    assert report["score"] >= 0.95
    assert report["decision"] == "pass"


def test_quality_scorer_rejects_repetitive_wrong_metric_template(tmp_path) -> None:
    from draftpaper_cli.manuscript_quality import assess_results_manuscript_quality, build_results_narrative_contract

    project = _quality_project(tmp_path)
    contract = build_results_narrative_contract(project)
    repeated = "The interpretation remains limited to the verified data, method design, and validation setting."
    text = "\\section{Results}\n" + " ".join([
        "Figure 1 provides the main empirical pattern.",
        "The reported F1=0.5 places the model near chance.",
        repeated, repeated, repeated,
    ])

    report = assess_results_manuscript_quality(project, text=text, contract=contract)

    assert report["score"] < 0.6
    assert report["decision"] == "repair_required"
    assert {item["kind"] for item in report["issues"]} >= {"untraceable_metric_claim", "missing_narrative_roles", "repetitive_template_prose"}


def test_results_section_packet_contains_narrative_contract(tmp_path) -> None:
    from draftpaper_cli.manuscript_composer import build_section_evidence_packet

    project = _quality_project(tmp_path)
    packet = build_section_evidence_packet(project, "results")

    assert packet["results_narrative_contract"]["minimum_quality_score"] == 0.95
    assert len(packet["results_narrative_contract"]["figure_groups"]) == 5


def test_submit_results_candidate_rejects_scientifically_thin_prose(tmp_path) -> None:
    import pytest

    from draftpaper_cli.manuscript_composer import SectionCompositionError, submit_section_draft

    project = _quality_project(tmp_path)
    candidate = project / "thin_results.tex"
    candidate.write_text(
        "\\section{Results}\nFigure 1 presents the first output. Figure 2 presents another output. "
        "The remaining figures summarize the completed analysis.",
        encoding="utf-8",
    )

    with pytest.raises(SectionCompositionError, match="quality contract"):
        submit_section_draft(project, "results", candidate)
