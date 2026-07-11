"""Structured blind-review evidence for a 95% manuscript-quality claim."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_repository import ArtifactRepository
from .project_scaffold import utc_now
from .project_state import load_project


TEMPLATE_PATH = "quality_checks/blind_manuscript_evaluation_template.json"
EVALUATION_PATH = "quality_checks/blind_manuscript_evaluation.json"
RUBRIC_DIMENSIONS = (
    "scientific_story_and_main_figure_narrative",
    "results_evidence_interpretation_and_comparison",
    "reproducible_data_and_methods_expression",
    "introduction_problem_gap_and_contribution",
    "discussion_comparison_mechanism_limitation_innovation",
    "figure_readability_panel_logic_and_captions",
    "prose_naturalness_and_cross_section_coherence",
)


class BlindQualityError(RuntimeError):
    """Raised when blind-review evidence is incomplete or internally invalid."""


def prepare_blind_quality_evaluation(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    repo = ArtifactRepository(state.path)
    reviewer_template = {
        "reviewer_id": "replace_with_anonymous_id",
        "manuscripts_blinded": True,
        "full_manuscript_compared": True,
        "real_figures_compared": True,
        "scientific_correctness_score": None,
        "dimension_scores": {dimension: None for dimension in RUBRIC_DIMENSIONS},
        "overall_quality_ratio": None,
        "notes": "",
    }
    payload = {
        "schema_version": "v0.23.0",
        "status": "pending_independent_review",
        "instructions": "Collect at least two independent blinded reviews of the complete manuscript and real figures. Scores must be evidence-based; do not infer them from automated keyword or metadata checks.",
        "minimum_reviewer_count": 2,
        "minimum_quality_ratio": 0.95,
        "required_scientific_correctness_score": 1.0,
        "rubric_dimensions": list(RUBRIC_DIMENSIONS),
        "reviews": [reviewer_template, {**reviewer_template, "reviewer_id": "replace_with_second_anonymous_id"}],
    }
    repo.write_json(TEMPLATE_PATH, payload)
    return {"status": "template_written", "project_path": str(state.path), "template": TEMPLATE_PATH}


def _score(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise BlindQualityError(f"Blind review field {field} must be numeric.") from exc
    if not 0.0 <= numeric <= 1.0:
        raise BlindQualityError(f"Blind review field {field} must be between 0 and 1.")
    return numeric


def record_blind_quality_evaluation(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise BlindQualityError(f"Cannot read blind-review input: {exc}") from exc
    if not isinstance(payload, dict):
        raise BlindQualityError("Blind-review input must contain a JSON object.")
    reviews = [item for item in payload.get("reviews") or [] if isinstance(item, dict)]
    if len(reviews) < 2:
        raise BlindQualityError("At least two independent blind reviews are required.")
    reviewer_ids = [str(item.get("reviewer_id") or "").strip() for item in reviews]
    if not all(reviewer_ids) or len(set(reviewer_ids)) != len(reviewer_ids):
        raise BlindQualityError("Reviewer IDs must be non-empty, anonymous, and unique.")
    normalized_reviews = []
    for review in reviews:
        if not all(review.get(field) is True for field in ("manuscripts_blinded", "full_manuscript_compared", "real_figures_compared")):
            raise BlindQualityError("Every reviewer must confirm blinding, complete-manuscript comparison, and real-figure comparison.")
        dimension_scores = review.get("dimension_scores") if isinstance(review.get("dimension_scores"), dict) else {}
        missing = [dimension for dimension in RUBRIC_DIMENSIONS if dimension not in dimension_scores]
        if missing:
            raise BlindQualityError("Blind review is missing rubric dimensions: " + ", ".join(missing))
        normalized_dimensions = {dimension: _score(dimension_scores[dimension], dimension) for dimension in RUBRIC_DIMENSIONS}
        normalized_reviews.append({
            **review,
            "scientific_correctness_score": _score(review.get("scientific_correctness_score"), "scientific_correctness_score"),
            "dimension_scores": normalized_dimensions,
            "overall_quality_ratio": _score(review.get("overall_quality_ratio"), "overall_quality_ratio"),
        })
    aggregate_quality = round(sum(item["overall_quality_ratio"] for item in normalized_reviews) / len(normalized_reviews), 4)
    scientific_correctness = min(item["scientific_correctness_score"] for item in normalized_reviews)
    result = {
        "schema_version": "v0.23.0",
        "status": "completed",
        "recorded_at": utc_now(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "manuscripts_blinded": True,
        "reviewer_count": len(normalized_reviews),
        "full_manuscript_compared": True,
        "real_figures_compared": True,
        "scientific_correctness_score": scientific_correctness,
        "aggregate_quality_ratio": aggregate_quality,
        "rubric_dimensions": list(RUBRIC_DIMENSIONS),
        "reviews": normalized_reviews,
        "quality_claim_eligible": scientific_correctness == 1.0 and aggregate_quality >= 0.95,
        "policy": "Blind review records human evaluation evidence; it cannot be generated from automated keyword, metadata, or file-presence scores.",
    }
    ArtifactRepository(state.path).write_json(EVALUATION_PATH, result)
    return result
