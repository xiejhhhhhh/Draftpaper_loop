from __future__ import annotations

from typing import Any

from .base import issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    result_validity = context.get("result_validity") or {}
    figures = context.get("figure_metadata") or []
    gaps = [
        issue_payload(
            code="default_claim_evidence_alignment",
            title="Check claim strength against available evidence",
            severity="major",
            target_stage="research_plan",
            rationale="The manuscript needs an explicit audit that each major claim is supported by data, method outputs, and result artifacts.",
            actions=[
                "map each major result claim to the figure, table, or metric that supports it",
                "downgrade claims that are only supported by conditional or exploratory evidence",
                "rerun Results and Discussion after the claim boundary is confirmed",
            ],
            requires_user_confirmation=True,
            confirmation_question="Should the manuscript be framed as confirmatory, exploratory, or descriptive?",
        )
    ]
    if result_validity.get("decision") in {"revise_required", "conditional_pass"}:
        gaps.append(issue_payload(
            code="default_result_validity_followup",
            title="Resolve conditional or failed result validity before final review",
            severity="major" if result_validity.get("decision") == "conditional_pass" else "blocking",
            target_stage="result_validity",
            rationale="The result validity gate is not a strong pass, so downstream manuscript claims need reviewer-style scrutiny.",
            actions=[
                "inspect the primary metric semantics and threshold",
                "confirm whether additional robustness or sensitivity analyses are needed",
                "rerun result validity before rewriting Results",
            ],
        ))
    if not figures:
        gaps.append(issue_payload(
            code="default_result_artifact_review_missing",
            title="Reviewable figure metadata is missing",
            severity="major",
            target_stage="results",
            rationale="A reviewer-engineering pass needs figure metadata to connect result claims to empirical outputs.",
            actions=[
                "rerun plan-figures and generate-analysis-code if empirical figures are expected",
                "run verify-methods with results/figure_metadata.json as a declared output",
            ],
        ))
    return gaps
