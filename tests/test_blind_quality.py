from __future__ import annotations

import json

import pytest

from draftpaper_cli.blind_quality import (
    BlindQualityError,
    RUBRIC_DIMENSIONS,
    prepare_blind_quality_evaluation,
    record_blind_quality_evaluation,
)
from draftpaper_cli.project_scaffold import create_project


def _review(reviewer_id: str, score: float = 0.97) -> dict[str, object]:
    return {
        "reviewer_id": reviewer_id,
        "manuscripts_blinded": True,
        "full_manuscript_compared": True,
        "real_figures_compared": True,
        "scientific_correctness_score": 1.0,
        "dimension_scores": {dimension: score for dimension in RUBRIC_DIMENSIONS},
        "overall_quality_ratio": score,
        "notes": "Independent blind comparison completed.",
    }


def test_prepare_and_record_blind_quality_evidence(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Blind review", field="engineering").path
    prepared = prepare_blind_quality_evaluation(project)
    completed = tmp_path / "completed_review.json"
    completed.write_text(json.dumps({"reviews": [_review("reviewer-a"), _review("reviewer-b", 0.96)]}), encoding="utf-8")

    report = record_blind_quality_evaluation(project, completed)

    assert prepared["status"] == "template_written"
    assert report["status"] == "completed"
    assert report["reviewer_count"] == 2
    assert report["aggregate_quality_ratio"] == 0.965
    assert report["quality_claim_eligible"] is True
    assert (project / "quality_checks" / "blind_manuscript_evaluation.json").is_file()


def test_blind_quality_rejects_single_or_unblinded_review(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Blind review failure", field="engineering").path
    completed = tmp_path / "invalid_review.json"
    review = _review("reviewer-a")
    review["manuscripts_blinded"] = False
    completed.write_text(json.dumps({"reviews": [review]}), encoding="utf-8")

    with pytest.raises(BlindQualityError):
        record_blind_quality_evaluation(project, completed)
