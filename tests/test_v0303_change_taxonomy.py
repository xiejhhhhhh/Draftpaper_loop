from __future__ import annotations

from draftpaper_cli.artifact_dag import stage_roots_for_change
from draftpaper_cli.change_impact import (
    CANONICAL_CHANGE_CLASSES,
    CHANGE_CLASS_SPECS,
    affected_stages_for_class,
    normalize_change_class,
)
from draftpaper_cli.manuscript_revision import _classify as classify_manuscript_revision
from draftpaper_cli.revision_transaction import _classify as classify_section_revision


EXPECTED_CLASSES = (
    "metadata_only",
    "presentation_only",
    "prose_only",
    "citation_change",
    "claim_boundary_change",
    "result_interpretation_change",
    "figure_change",
    "metrics_change",
    "run_change",
    "method_change",
    "data_change",
    "cohort_change",
    "research_plan_change",
)


def test_change_taxonomy_has_one_authoritative_contract() -> None:
    assert CANONICAL_CHANGE_CLASSES == EXPECTED_CLASSES
    assert tuple(CHANGE_CLASS_SPECS) == EXPECTED_CLASSES
    for name, spec in CHANGE_CLASS_SPECS.items():
        assert spec.change_class == name
        assert isinstance(spec.affected_stages, tuple)
        assert isinstance(spec.reopen_evidence, bool)
        assert isinstance(spec.rerun_science, bool)
        assert isinstance(spec.rerun_review, bool)
        assert isinstance(spec.release_only, bool)


def test_legacy_change_names_normalize_without_defining_a_second_taxonomy() -> None:
    expected = {
        "citation_local": "citation_change",
        "prose_semantic_no_evidence_change": "prose_only",
        "metadata_claim_change": "claim_boundary_change",
        "cohort_definition_change": "cohort_change",
        "analysis_spec_change": "method_change",
        "run_output_change": "run_change",
        "figure_semantic_change": "figure_change",
        "claim_contract_change": "research_plan_change",
        "reference_metadata_only": "metadata_only",
        "scientific_result": "metrics_change",
        "method_semantic": "method_change",
        "data_semantic": "data_change",
        "research_design": "research_plan_change",
        "citation_edit": "citation_change",
        "claim_narrowing": "claim_boundary_change",
        "result_interpretation": "result_interpretation_change",
        "scientific_evidence_change": "research_plan_change",
        "language_only": "prose_only",
    }
    assert {name: normalize_change_class(name) for name in expected} == expected


def test_artifact_stage_roots_are_consistent_with_authoritative_affected_stages() -> None:
    section_stage = {
        "metadata_only": None,
        "presentation_only": None,
        "prose_only": "methods_writing",
        "citation_change": "discussion",
        "claim_boundary_change": "results",
        "result_interpretation_change": "results",
        "figure_change": None,
        "metrics_change": None,
        "run_change": None,
        "method_change": None,
        "data_change": None,
        "cohort_change": None,
        "research_plan_change": None,
    }
    for change_class in CANONICAL_CHANGE_CLASSES:
        section = "methods" if change_class == "prose_only" else "discussion" if change_class == "citation_change" else None
        roots = stage_roots_for_change(change_class, section=section)
        affected = affected_stages_for_class(change_class, source_stage=section_stage[change_class])
        assert set(roots).issubset(affected), (change_class, roots, affected)


def test_methods_and_discussion_revisions_start_from_the_edited_section() -> None:
    assert stage_roots_for_change("prose_only", section="methods") == ["methods_writing"]
    assert stage_roots_for_change("prose_only", section="discussion") == ["discussion"]
    assert stage_roots_for_change("citation_change", section="discussion") == ["discussion"]
    assert stage_roots_for_change("claim_boundary_change") == ["results"]


def test_revision_classifiers_emit_only_canonical_names() -> None:
    before = "A result is reported."
    after = "A result is reported with clearer wording."
    changed_citation = after + " \\citep{Example2026}."

    assert classify_section_revision(before, after, None) == "prose_only"
    assert classify_section_revision(before, changed_citation, None) == "citation_change"
    assert classify_section_revision(before, after, "citation_local") == "citation_change"

    change_class, stale, citation_bearing = classify_manuscript_revision(
        "results",
        "Narrow the interpretation to the validated cohort.",
        "The conclusion is limited to the held-out cohort.",
    )
    assert change_class == "claim_boundary_change"
    assert "results" in stale and "discussion" in stale
    assert citation_bearing is True


def test_scientific_change_specs_reopen_only_the_required_chain() -> None:
    assert CHANGE_CLASS_SPECS["metadata_only"].release_only is True
    assert CHANGE_CLASS_SPECS["metadata_only"].rerun_science is False
    assert CHANGE_CLASS_SPECS["claim_boundary_change"].reopen_evidence is False
    assert CHANGE_CLASS_SPECS["figure_change"].reopen_evidence is True
    assert CHANGE_CLASS_SPECS["figure_change"].rerun_science is False
    assert CHANGE_CLASS_SPECS["run_change"].rerun_science is True
    assert CHANGE_CLASS_SPECS["data_change"].rerun_science is True
