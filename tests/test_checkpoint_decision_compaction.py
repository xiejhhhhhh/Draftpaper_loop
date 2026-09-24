from __future__ import annotations

import copy
from pathlib import Path

import pytest

from draftpaper_cli.checkpoint_brief import build_human_decision_brief
from draftpaper_cli.checkpoint_fingerprint import build_scientific_decision_fingerprint, compare_scientific_decisions
from draftpaper_cli.checkpoint_html import render_checkpoint_decision_html
from draftpaper_cli.checkpoint_readability import build_checkpoint_readability_report
from draftpaper_cli.figure_claim_map import build_figure_claim_map


def _summary(*, value: float, duplicate_counts: bool) -> dict:
    sample_flow = [
        {
            "count_definition_id": f"sample_category_{index}_post_filter_records",
            "entity_type": "sample_record",
            "count_mode": "post_filter_row_count",
            "cohort_id": f"cohort:registered_validation_population_{index}",
            "filter_contract_id": f"filter:quality_eligibility_screen_for_population_{index}",
            "value": 1100 + index,
            "source_paths": ["results/count_identity_report.json"],
        }
        for index in range(9)
    ]
    return {
        "checkpoint_type": "core_evidence",
        "completed_stage": "core_evidence",
        "stage_purpose_zh": "Confirm the registered evidence and its scientific limits.",
        "identity": {
            "plan_hash": "plan-first" if value < 1 else "plan-revised",
            "run_id": "run-source-held-out-validation",
            "cohort_id": "cohort:controlled_validation_population",
            "sample_unit": "source",
            "cohort_label": "source-held-out",
            "analysis_spec_ids": [f"analysis:registered_method_and_resampling_contract_{i}" for i in range(6)],
            "method_analysis_contract_sha256": "a" * 64 if value < 1 else "b" * 64,
        },
        "core_metrics": {
            "metric": "macro-F1",
            "metric_definition_id": "macro-f1-definition-v1",
            "value": value,
            "uncertainty": "bootstrap-95ci",
            "run_id": "run-source-held-out-validation",
            "cohort_id": "cohort:controlled_validation_population",
            "sample_unit": "source",
            "validation_design": "source-held-out",
            "split_id": "fixed-source-holdout-split-v1",
            "model_id": "registered-baseline-model",
            "aggregation_id": "macro-over-held-out-classes",
            "metric_source": "results/tables/verified_metric_evidence.csv",
            "sample_flow": sample_flow * (2 if duplicate_counts else 1),
        },
        "key_findings": [
            {"summary_zh": f"Registered primary macro-F1 = {value}; this is not an external generalization result."},
            {"summary_zh": "The controlled study does not measure deployment throughput or population-wide causal effects."},
        ],
        "claim_boundaries": [
            {"summary_zh": f"Boundary {i}: Conclusions apply only to the registered population and validation design; "
             "do not extrapolate to unobserved groups or interpret this comparison as a causal effect."}
            for i in range(5)
        ],
        "stage_deliverables": [
            {
                "deliverable_group": "figure",
                "project_relative_path": f"results/figures/fig_{i}.png",
                "title_zh": f"Figure {i}: Registered sample selection, model comparison and held-out uncertainty analysis.",
                "after_semantic_sha256": ("a" if value < 1 else "b") * 64,
                "caption": f"Panel {i} reports the registered evaluation and its uncertainty.",
                "caption_en": f"Panel {i} reports the registered evaluation and its uncertainty.",
                "split_id": "fixed-source-holdout-split-v1",
                "cohort_id": "cohort:controlled_validation_population",
                "caption_split_id": "fixed-source-holdout-split-v1",
                "caption_cohort_id": "cohort:controlled_validation_population",
                "series_ids": ["primary"],
                "caption_series_ids": ["primary"],
                "claim_series_ids": ["primary"],
                "quantity_kind": "class_conditional_rate",
                "caption_quantity_kind": "class_conditional_rate",
                "claim_quantity_kind": "class_conditional_rate",
            }
            for i in range(1, 7)
        ],
        "review_state": "confirmable",
        "confirmation_meaning_zh": "Proceed only with the registered evidence after confirmation.",
    }


def _package() -> dict:
    old = _summary(value=0.5, duplicate_counts=False)
    current = _summary(value=1.0, duplicate_counts=True)
    old_brief = build_human_decision_brief(old)
    brief = build_human_decision_brief(current)
    old_fingerprint = build_scientific_decision_fingerprint(old, old_brief, figure_claim_map=build_figure_claim_map(old, old_brief))
    fingerprint = build_scientific_decision_fingerprint(current, brief, figure_claim_map=build_figure_claim_map(current, brief))
    brief["semantic_delta"] = compare_scientific_decisions(old_fingerprint, fingerprint)
    return {
        **current,
        "schema_version": "dpl.checkpoint_summary.v6",
        "decision_brief": brief,
        "scientific_decision_fingerprint": fingerprint,
        "confirmation_contract": {"confirmation_command_allowed": False},
    }


@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_long_bilingual_decision_is_compact_without_losing_review_content(tmp_path: Path, locale: str) -> None:
    summary = _package()
    original = copy.deepcopy(summary)
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale=locale)
    report = build_checkpoint_readability_report(html=html, brief=summary["decision_brief"], locale=locale)

    assert report["status"] == "passed", report
    assert report["visible_character_count"] <= 20000
    assert report["checks"]["rendered_fact_coverage"]
    assert report["checks"]["rendered_statement_coverage"]
    for token in ("macro-F1", "1.0", "0.5", "bootstrap-95ci", "source-held-out", "registered-baseline-model",
                  "run-source-held-out-validation", "fixed-source-holdout-split-v1", "macro-over-held-out-classes"):
        assert token in html
    for index in range(9):
        assert str(1100 + index) in html
        assert f"filter:quality_eligibility_screen_for_population_{index}" in html
    for index in range(5):
        assert f"Boundary {index}: Conclusions apply only to the registered population" in html
    for index in range(1, 7):
        assert f'Figure {index}: Registered sample selection' in html
        assert f'id="figure-evidence-figure-{index}"' in html
    assert summary == original


@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_only_exact_duplicate_facts_share_a_visible_row(tmp_path: Path, locale: str) -> None:
    summary = _summary(value=1.0, duplicate_counts=False)
    base = summary["core_metrics"]["sample_flow"][0]
    summary["core_metrics"]["sample_flow"] = [
        base,
        copy.deepcopy(base),
        {**base, "cohort_id": "cohort:different_population"},
        {**base, "filter_contract_id": "filter:different_selection"},
        {**base, "source_paths": ["results/independent_count_evidence.json"]},
        {**base, "count_definition_id": "Different meaning with the same value"},
    ]
    brief = build_human_decision_brief(summary)
    summary["decision_brief"] = brief
    original = copy.deepcopy(summary)
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale=locale)
    heading = "Key facts for this decision" if locale == "en" else "本次决定的关键事实"
    facts_html = html.split(f"<h2>{heading}</h2>")[1].split("</section>")[0]

    assert facts_html.count("sample_category_0_post_filter_records") == 4
    assert "Different meaning with the same value" in facts_html
    assert "cohort:different_population" in facts_html
    assert "filter:different_selection" in facts_html
    assert "results/independent_count_evidence.json" in facts_html
    report = build_checkpoint_readability_report(html=html, brief=brief, locale=locale)
    assert set(report["expected_fact_ids"]) <= set(report["rendered_fact_ids"])
    count_ids = [fact["fact_id"] for fact in brief["facts"] if fact["fact_type"] == "count"]
    assert all(fact_id in facts_html for fact_id in count_ids)
    assert summary == original


@pytest.mark.parametrize("locale", ["zh-CN", "en"])
def test_semantic_list_changes_omit_unchanged_entries_but_preserve_multiplicity(tmp_path: Path, locale: str) -> None:
    summary = _package()
    unchanged = {"finding": "UNCHANGED_RESULT_WITH_NO_SEMANTIC_DIFFERENCE"}
    repeated = {"finding": "REPEATED_ENTRY_WITH_ONE_REMOVAL"}
    summary["decision_brief"]["semantic_delta"]["changes"] = [{
        "field": "decision_brief.semantic_subject.confirming",
        "before": [unchanged, repeated, repeated, {"metric": "macro-F1", "value": 0.5, "run_id": "previous-run"}],
        "after": [{"metric": "macro-F1", "value": 1.0, "run_id": "current-run"}, repeated, unchanged],
    }]
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale=locale)
    delta_html = html.split('<section class="section">', 1)[1].split("</section>", 1)[0]

    assert "UNCHANGED_RESULT_WITH_NO_SEMANTIC_DIFFERENCE" not in delta_html
    assert delta_html.count("REPEATED_ENTRY_WITH_ONE_REMOVAL") == 1
    assert "previous-run" in delta_html and "current-run" in delta_html
    assert "0.5" in delta_html and "1.0" in delta_html


def test_hash_only_list_change_remains_explained_in_words(tmp_path: Path) -> None:
    summary = _package()
    summary["decision_brief"]["semantic_delta"]["changes"] = [{
        "field": "decision_brief.semantic_subject.figure_claims",
        "before": [{"figure_id": "Figure 6 uncertainty analysis", "semantic_sha256": "a" * 64}],
        "after": [{"figure_id": "Figure 6 uncertainty analysis", "semantic_sha256": "b" * 64}],
    }]
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    delta_html = html.split('<section class="section">', 1)[1].split("</section>", 1)[0]
    assert "Figure 6 uncertainty analysis" in delta_html
    assert "content identity changed" in delta_html
    assert "a" * 64 not in delta_html and "b" * 64 not in delta_html


def test_unique_oversized_facts_are_not_truncated_to_bypass_readability(tmp_path: Path) -> None:
    summary = _summary(value=1.0, duplicate_counts=False)
    summary["identity"]["analysis_spec_ids"] = ["unique_scientific_contract_" + "x" * 21000]
    brief = build_human_decision_brief(summary)
    summary["decision_brief"] = brief
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    report = build_checkpoint_readability_report(html=html, brief=brief, locale="en")
    assert report["status"] == "blocked"
    assert "visible_chars_within_budget" in report["failure_codes"]
    assert "unique_scientific_contract_" + "x" * 21000 in html


def test_unrecognized_ordered_scientific_lists_keep_their_before_and_after_order(tmp_path: Path) -> None:
    summary = _package()
    summary["decision_brief"]["semantic_delta"]["changes"] = [{
        "field": "scientific_identity.preprocessing_steps",
        "before": ["fit-normalizer", "holdout-split"],
        "after": ["holdout-split", "fit-normalizer"],
    }]
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    delta_html = html.split('<section class="section">', 1)[1].split("</section>", 1)[0]
    assert "fit-normalizer, holdout-split" in delta_html
    assert "holdout-split, fit-normalizer" in delta_html
    assert "scientific content is unchanged" not in delta_html


def test_reordered_statement_set_is_not_repeated_as_two_full_lists(tmp_path: Path) -> None:
    summary = _package()
    summary["decision_brief"]["semantic_delta"]["changes"] = [{
        "field": "decision_brief.semantic_subject.confirming",
        "before": [{"finding": "First registered claim"}, {"finding": "Second registered claim"}],
        "after": [{"finding": "Second registered claim"}, {"finding": "First registered claim"}],
    }]
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    delta_html = html.split('<section class="section">', 1)[1].split("</section>", 1)[0]
    assert "Only list ordering changed" in delta_html
    assert "First registered claim" not in delta_html
