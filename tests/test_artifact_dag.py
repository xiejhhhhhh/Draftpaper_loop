from draftpaper_cli.artifact_dag import stale_artifacts_for_change


def test_formula_or_local_methods_prose_revision_does_not_reopen_data_or_figures() -> None:
    stale = stale_artifacts_for_change("prose_semantic_no_evidence_change", section="methods")
    assert "methods" in stale
    assert "dependent_discussion_claims" in stale
    assert "figures" not in stale
    assert "data_semantics" not in stale


def test_citation_local_change_only_reopens_manuscript_release_chain() -> None:
    stale = stale_artifacts_for_change("citation_local", section="discussion")
    assert {"discussion", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"}.issubset(stale)
    assert "analysis_execution" not in stale
    assert "figures" not in stale


def test_cohort_change_reopens_scientific_chain() -> None:
    stale = stale_artifacts_for_change("cohort_definition_change")
    assert {"data_semantics", "analysis_execution", "figures", "core_evidence", "results", "methods"}.issubset(stale)
